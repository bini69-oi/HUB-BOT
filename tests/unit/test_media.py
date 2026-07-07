"""photo_input: local uploads file -> FSInputFile; file_id / URL -> passthrough."""

from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile

from src.bot.media import photo_input


def test_file_id_passthrough() -> None:
    assert photo_input("AgACAgIAAxkBAAExample") == "AgACAgIAAxkBAAExample"


def test_url_passthrough() -> None:
    assert photo_input("https://example.com/logo.png") == "https://example.com/logo.png"


def test_local_file_becomes_fsinput(tmp_path: Path) -> None:
    f = tmp_path / "logo.png"
    f.write_bytes(b"x")
    assert isinstance(photo_input(str(f)), FSInputFile)


def test_missing_local_path_passthrough() -> None:
    # a non-existent path stays a string (Telegram will simply reject it)
    assert photo_input("uploads/nope.png") == "uploads/nope.png"


def test_blank_is_empty() -> None:
    assert photo_input("   ") == ""
