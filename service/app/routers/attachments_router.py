"""Attachment upload, download, preview, delete."""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..services import attachments, store

router = APIRouter(prefix="/api", tags=["attachments"])


@router.post("/cards/{card_id}/attachments", status_code=201)
async def upload(card_id: int, file: UploadFile, request: Request):
    if not store.get_card(card_id):
        raise HTTPException(404)
    data = await file.read()
    try:
        saved = attachments.save(card_id, file.filename or "file", data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    from ..services import card_events
    from .boards import actor

    card_events.log(card_id, actor(request), "attached", saved["filename"])
    return saved


@router.get("/cards/{card_id}/attachments")
def list_attachments(card_id: int):
    if not store.get_card(card_id):
        raise HTTPException(404)
    return attachments.list_for_card(card_id)


@router.get("/attachments/{attachment_id}/file")
def download(attachment_id: int):
    att = attachments.get(attachment_id)
    if not att:
        raise HTTPException(404)
    path = attachments.path_for(att)
    if not path.is_file():
        raise HTTPException(410, "the stored file is gone")
    return FileResponse(
        path,
        filename=att["filename"],
        content_disposition_type="inline",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(att['filename'])}"
        },
    )


@router.get("/attachments/{attachment_id}/preview")
def preview(attachment_id: int):
    att = attachments.get(attachment_id)
    if not att:
        raise HTTPException(404)
    return attachments.preview(att)


@router.get("/attachments/{attachment_id}/as-stl")
def as_stl(attachment_id: int):
    """3MF and OBJ converted to STL on the fly (cached) so the 3D viewer
    can render them."""
    from fastapi.responses import Response

    from ..services import mesh_convert

    att = attachments.get(attachment_id)
    if not att:
        raise HTTPException(404)
    ext = att["filename"].rsplit(".", 1)[-1].lower()
    if ext not in attachments.CONVERTIBLE_MESH_EXTS:
        raise HTTPException(422, "only 3MF and OBJ convert to STL")
    source = attachments.path_for(att)
    if not source.is_file():
        raise HTTPException(410, "the stored file is gone")
    cache = source.with_suffix(source.suffix + ".stl")
    if not cache.is_file() or cache.stat().st_mtime < source.stat().st_mtime:
        try:
            data = (
                mesh_convert.threemf_to_stl(source)
                if ext == "3mf"
                else mesh_convert.obj_to_stl(source)
            )
        except mesh_convert.ConvertError as exc:
            raise HTTPException(422, str(exc))
        cache.write_bytes(data)
    return Response(cache.read_bytes(), media_type="model/stl")


@router.get("/attachments/{attachment_id}/embedded-preview")
def embedded_preview(attachment_id: int):
    """The preview image a SolidWorks file carries inside its container."""
    from fastapi.responses import Response

    from ..services import mesh_convert

    att = attachments.get(attachment_id)
    if not att:
        raise HTTPException(404)
    path = attachments.path_for(att)
    if not path.is_file():
        raise HTTPException(410, "the stored file is gone")
    found = mesh_convert.extract_embedded_preview(path)
    if not found:
        raise HTTPException(404, "no embedded preview in this file")
    data, mime = found
    return Response(data, media_type=mime)


@router.get("/attachments/{attachment_id}/file-as-pdf")
def file_as_pdf(attachment_id: int):
    """Illustrator files saved with PDF compatibility, served as PDF so
    the browser's viewer renders them."""
    att = attachments.get(attachment_id)
    if not att:
        raise HTTPException(404)
    path = attachments.path_for(att)
    if not path.is_file():
        raise HTTPException(410, "the stored file is gone")
    return FileResponse(path, media_type="application/pdf", filename=att["filename"],
                        content_disposition_type="inline")


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete(attachment_id: int):
    if not attachments.delete(attachment_id):
        raise HTTPException(404)
