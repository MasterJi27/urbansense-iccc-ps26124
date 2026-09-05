"""Safe filename helpers for evidence storage (DPDP: no path traversal)."""

from __future__ import annotations

from pathlib import Path

_DEFAULT = "evidence.bin"


def safe_filename(filename: str | None, default: str = _DEFAULT, max_len: int = 128) -> str:
    name = Path(filename).name if filename else default
    if not name or name in {".", ".."}:
        name = default
    cleaned = []
    for ch in name:
        cleaned.append(ch if ch.isalnum() or ch in "._-" else "_")
    name = "".join(cleaned).lstrip("._")
    if not name:
        name = default
    if len(name) > max_len:
        if "." in name:
            base, ext = name.rsplit(".", 1)
            name = f"{base[: max(1, max_len - len(ext) - 1)]}.{ext}"
        else:
            name = name[:max_len]
    return name or default
