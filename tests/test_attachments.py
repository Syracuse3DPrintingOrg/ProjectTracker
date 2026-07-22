import io
import zipfile

from app.services import attachments, llm


def make_card(client):
    p = client.post("/api/projects", json={"name": "Shop"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Bracket",
        "description": "- [x] measure\n- [ ] print", "due_date": "2026-08-01"}).json()
    return p, card


def upload(client, card_id, name, data):
    return client.post(
        f"/api/cards/{card_id}/attachments",
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
    )


def test_upload_list_download_delete(client):
    p, card = make_card(client)
    resp = upload(client, card["id"], "notes.txt", b"hello world")
    assert resp.status_code == 201
    att = resp.json()
    assert att["filename"] == "notes.txt" and att["size"] == 11

    assert [a["id"] for a in client.get(f"/api/cards/{card['id']}/attachments").json()] == [att["id"]]
    got = client.get(f"/api/attachments/{att['id']}/file")
    assert got.content == b"hello world"

    assert client.delete(f"/api/attachments/{att['id']}").status_code == 204
    assert client.get(f"/api/attachments/{att['id']}/file").status_code == 404
    assert upload(client, 9999, "x.txt", b"data").status_code == 404
    assert upload(client, card["id"], "empty.txt", b"").status_code == 422


def test_filename_sanitized(client):
    p, card = make_card(client)
    att = upload(client, card["id"], "../../etc/passwd", b"nope").json()
    assert att["filename"] == "passwd"
    stored = attachments.get(att["id"])["stored"]
    assert "/" not in stored and ".." not in stored


def test_deleting_card_removes_files(client):
    p, card = make_card(client)
    att = upload(client, card["id"], "a.txt", b"data").json()
    path = attachments.path_for(attachments.get(att["id"]))
    assert path.is_file()
    client.delete(f"/api/cards/{card['id']}")
    assert not path.is_file()


def test_preview_csv(client):
    p, card = make_card(client)
    att = upload(client, card["id"], "parts.csv", b"name,qty\nbolt,4\nnut,4\n").json()
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "table"
    assert pv["columns"] == ["name", "qty"]
    assert pv["rows"] == [["bolt", "4"], ["nut", "4"]]
    assert pv["truncated"] is False


def test_preview_xlsx(client, tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["part", "mm"])
    ws.append(["rail", 120])
    buf = io.BytesIO()
    wb.save(buf)

    p, card = make_card(client)
    att = upload(client, card["id"], "cuts.xlsx", buf.getvalue()).json()
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "table"
    assert pv["columns"] == ["part", "mm"]
    assert pv["rows"] == [["rail", "120"]]


def test_preview_docx(client):
    buf = io.BytesIO()
    doc_xml = (
        '<?xml version="1.0"?><w:document'
        ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Plan the build</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Cut twice, measure once &amp; regret.</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc_xml)

    p, card = make_card(client)
    att = upload(client, card["id"], "plan.docx", buf.getvalue()).json()
    pv = client.get(f"/api/attachments/{att['id']}/preview").json()
    assert pv["kind"] == "text"
    assert "Plan the build" in pv["text"]
    assert "measure once & regret" in pv["text"]


def test_preview_kinds_by_extension(client):
    p, card = make_card(client)
    cases = {
        "photo.png": "image",
        "spec.pdf": "pdf",
        "bracket.stl": "stl",
        "bracket.step": "step",
        "housing.stp": "step",
        "bracket.sldprt": "model-unsupported",
        "firmware.bin": "binary",
        "notes.md": "text",
    }
    for name, kind in cases.items():
        att = upload(client, card["id"], name, b"x" * 10).json()
        pv = client.get(f"/api/attachments/{att['id']}/preview").json()
        assert pv["kind"] == kind, name
    # Corrupt xlsx reports a friendly error instead of a 500.
    att = upload(client, card["id"], "broken.xlsx", b"not a zip").json()
    assert client.get(f"/api/attachments/{att['id']}/preview").json()["kind"] == "error"


def test_research_endpoint(client, monkeypatch):
    p, card = make_card(client)
    assert client.post("/api/assist/research", json={"card_id": card["id"]}).status_code == 400
    monkeypatch.setattr(llm, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(llm, "research", lambda t, d, pr: "## Approaches\nDo it well.")
    data = client.post("/api/assist/research", json={"card_id": card["id"]}).json()
    assert data["research"].startswith("## Approaches")


def test_handoff_prompt(client):
    p, card = make_card(client)
    upload(client, card["id"], "drawing.pdf", b"pdf")
    data = client.get(f"/api/cards/{card['id']}/handoff").json()
    prompt = data["prompt"]
    assert "Task: Bracket" in prompt
    assert "Project: Shop" in prompt
    assert "Due: 2026-08-01" in prompt
    assert "- [x] measure" in prompt and "- [ ] print" in prompt
    assert "Checklist (1/2 done)" in prompt
    assert "drawing.pdf" in prompt
    assert data["title"] == "Bracket"
    assert client.get("/api/cards/999/handoff").status_code == 404
