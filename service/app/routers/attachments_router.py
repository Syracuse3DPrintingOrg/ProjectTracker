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


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete(attachment_id: int):
    if not attachments.delete(attachment_id):
        raise HTTPException(404)
