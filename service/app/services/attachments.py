"""Card attachments: any file, dragged onto a card, previewed in place.

Files live under data_dir/attachments as <uuid>.<ext> with the original
name kept in the database, so nothing user-controlled touches the
filesystem path. Previews are parsed server-side where a plain browser
cannot do it (CSV, Excel, Word); images, PDF, STL, and STEP go to the
browser raw, which renders them natively (STL through our own little
viewer, STEP tessellated in the browser by the vendored occt-import-js).
"""

import csv
import io
import re
import uuid
import zipfile
from pathlib import Path

from .. import config, database

MAX_SIZE = 100 * 1024 * 1024  # 100 MB, generous for meshes and archives

TABLE_ROW_CAP = 200
TABLE_COL_CAP = 30
TEXT_CAP = 60_000

TEXT_EXTS = {
    "txt", "md", "log", "json", "yaml", "yml", "toml", "ini", "py", "js",
    "html", "css", "sh", "c", "cpp", "h", "ino", "gcode", "scad", "xml",
}
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"}
MODEL_NOTES = {
    "sldprt": "SolidWorks parts are proprietary; export STEP for exchange or STL for an in-browser preview.",
    "sldasm": "SolidWorks assemblies are proprietary; export STEP for exchange or STL for an in-browser preview.",
    "3mf": "3MF preview is not built in yet; slice it or export STL for an in-browser preview.",
    "obj": "OBJ preview is not built in yet; export STL for an in-browser preview.",
}


def _dir() -> Path:
    d = config.DATA_DIR / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def save(card_id: int, filename: str, data: bytes) -> dict:
    filename = (filename or "file").strip().replace("\\", "/").split("/")[-1][:200]
    if not data:
        raise ValueError("the file is empty")
    if len(data) > MAX_SIZE:
        raise ValueError("files top out at 100 MB")
    ext = re.sub(r"[^a-z0-9]", "", _ext(filename))[:10]
    stored = f"{uuid.uuid4().hex}{'.' + ext if ext else ''}"
    (_dir() / stored).write_bytes(data)
    with database.connect() as conn:
        cur = conn.execute(
            "INSERT INTO attachments (card_id, filename, stored, size)"
            " VALUES (?, ?, ?, ?)",
            (card_id, filename, stored, len(data)),
        )
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def list_for_card(card_id: int) -> list[dict]:
    with database.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM attachments WHERE card_id = ? ORDER BY id",
                (card_id,),
            )
        ]


def get(attachment_id: int) -> dict | None:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
    return dict(row) if row else None


def path_for(att: dict) -> Path:
    return _dir() / att["stored"]


def delete(attachment_id: int) -> bool:
    att = get(attachment_id)
    if not att:
        return False
    with database.connect() as conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    try:
        path_for(att).unlink()
    except OSError:
        pass
    return True


def delete_files_for_card(card_id: int) -> None:
    """Remove stored files before a card row (and its cascade) goes."""
    for att in list_for_card(card_id):
        try:
            path_for(att).unlink()
        except OSError:
            pass


def delete_files_for_project(project_id: int) -> None:
    with database.connect() as conn:
        rows = conn.execute(
            "SELECT attachments.stored FROM attachments"
            " JOIN cards ON cards.id = attachments.card_id"
            " WHERE cards.project_id = ?",
            (project_id,),
        ).fetchall()
    for r in rows:
        try:
            (_dir() / r["stored"]).unlink()
        except OSError:
            pass


def counts_by_card(project_id: int) -> dict[int, int]:
    with database.connect() as conn:
        return {
            r["card_id"]: r["n"]
            for r in conn.execute(
                "SELECT card_id, COUNT(*) AS n FROM attachments"
                " JOIN cards ON cards.id = attachments.card_id"
                " WHERE cards.project_id = ? GROUP BY card_id",
                (project_id,),
            )
        }


# ---- preview ----

def preview(att: dict) -> dict:
    """What the browser should render for this attachment."""
    ext = _ext(att["filename"])
    url = f"/api/attachments/{att['id']}/file"
    base = {"name": att["filename"], "size": att["size"]}
    try:
        if ext == "csv":
            return {**base, **_preview_csv(path_for(att))}
        if ext == "xlsx":
            return {**base, **_preview_xlsx(path_for(att))}
        if ext == "docx":
            return {**base, **_preview_docx(path_for(att))}
        if ext in TEXT_EXTS:
            return {**base, **_preview_text(path_for(att))}
    except Exception as exc:
        return {**base, "kind": "error", "note": f"could not parse this file: {exc}"}
    if ext in IMAGE_EXTS:
        return {**base, "kind": "image", "url": url}
    if ext == "pdf":
        return {**base, "kind": "pdf", "url": url}
    if ext == "stl":
        return {**base, "kind": "stl", "url": url}
    if ext in ("step", "stp"):
        return {**base, "kind": "step", "url": url}
    if ext in MODEL_NOTES:
        return {**base, "kind": "model-unsupported", "note": MODEL_NOTES[ext]}
    return {**base, "kind": "binary", "note": "no preview for this type; download to open it"}


def _preview_csv(path: Path) -> dict:
    rows = []
    truncated = False
    with open(path, "r", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        for i, row in enumerate(csv.reader(f, dialect)):
            if i >= TABLE_ROW_CAP:
                truncated = True
                break
            rows.append([str(c) for c in row[:TABLE_COL_CAP]])
    columns = rows[0] if rows else []
    return {"kind": "table", "columns": columns, "rows": rows[1:], "truncated": truncated}


def _preview_xlsx(path: Path) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = []
    truncated = False
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= TABLE_ROW_CAP:
            truncated = True
            break
        rows.append(["" if c is None else str(c) for c in row[:TABLE_COL_CAP]])
    wb.close()
    columns = rows[0] if rows else []
    return {
        "kind": "table",
        "columns": columns,
        "rows": rows[1:],
        "truncated": truncated,
        "sheet": wb.sheetnames[0],
        "sheets": wb.sheetnames,
    }


def _preview_docx(path: Path) -> dict:
    """Word text without python-docx: a .docx is a zip; paragraphs are
    w:p elements in word/document.xml."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    paragraphs = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.DOTALL):
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.DOTALL))
        text = (
            text.replace("&amp;", "&").replace("&lt;", "<")
            .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
        )
        paragraphs.append(text)
    text = "\n\n".join(p for p in paragraphs if p.strip())
    truncated = len(text) > TEXT_CAP
    return {"kind": "text", "text": text[:TEXT_CAP], "truncated": truncated}


def _preview_text(path: Path) -> dict:
    data = path.read_bytes()[: TEXT_CAP + 1]
    text = data.decode("utf-8", errors="replace")
    return {"kind": "text", "text": text[:TEXT_CAP], "truncated": len(data) > TEXT_CAP}
