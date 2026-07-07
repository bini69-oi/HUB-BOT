"""Resolve a stored image reference into something aiogram can send.

Images reach the bot three ways: a Telegram ``file_id`` (set from the bot via /setlogo),
a public URL, or a local ``uploads/…`` path uploaded from the cabinet (served at /uploads).
The first two are sent as-is; a local file is wrapped in ``FSInputFile`` so the bot streams
it straight from disk — Telegram cannot fetch a server-local path.
"""

from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile


def photo_input(ref: str) -> str | FSInputFile:
    ref = ref.strip()
    if ref and not ref.startswith(("http://", "https://")) and Path(ref).is_file():
        return FSInputFile(ref)
    return ref
