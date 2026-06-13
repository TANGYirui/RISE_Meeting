"""User-controlled summary batch selection."""
from __future__ import annotations

from typing import Sequence

from .models import AgendaTopic


def next_summary_batch(
    topics: Sequence[AgendaTopic],
    *,
    batch_size: int = 10,
) -> tuple[list[AgendaTopic], int]:
    pending = [topic for topic in topics if topic.summary_status != "completed"]
    return pending[:batch_size], max(0, len(pending) - batch_size)

