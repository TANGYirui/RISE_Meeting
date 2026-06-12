"""Cross-platform console output helpers."""
from __future__ import annotations

from typing import Any


def configure_console_stream(stream: Any) -> None:
    """Prevent locale-specific terminals from crashing on Unicode output."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")
