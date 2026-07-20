"""Admin: media uploads (broadcast media, menu screen images, mini-app covers).

Files land in ``uploads/`` next to the app cwd and are served at ``/uploads/...``.
Extension whitelist + size cap; names are random uuids so paths are unguessable.
The audit trail happens where the file gets attached (broadcast / menu save).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.web.routes.admin.deps import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])

UPLOAD_DIR = Path("uploads")
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED = {
    ".jpg": "photo",
    ".jpeg": "photo",
    ".png": "photo",
    ".webp": "photo",
    ".gif": "gif",
    ".mp4": "video",
}


@router.post("/upload")
async def upload(file: UploadFile) -> dict[str, str]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"unsupported file type: {ext or '?'}")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large (max 20 MB)")
    name = f"{uuid.uuid4().hex}{ext}"
    try:
        UPLOAD_DIR.mkdir(exist_ok=True)
        (UPLOAD_DIR / name).write_bytes(data)
    except OSError as exc:
        # Docker installs mount `uploads` as a named volume; if it was created root-owned the
        # non-root app user can't write. Answer with a clear, fixable message instead of a raw
        # 500 (which the crash reporter would flag as a bug rather than a permissions setup issue).
        raise HTTPException(
            500,
            "не удалось сохранить файл в папку uploads (нет прав на запись). "
            "Docker: `docker compose run --rm --user root web chown -R app:app /app/uploads`.",
        ) from exc
    return {"path": f"uploads/{name}", "url": f"/uploads/{name}", "kind": ALLOWED[ext]}
