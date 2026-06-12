"""Storage conventions for experiment results and per-query workspaces."""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator


def default_result_root(repo_root: Path, run_name: str) -> Path:
    """Return the default persistent output directory for an experiment."""
    return repo_root / "result" / run_name


@contextmanager
def query_workspace(
    result_root: Path,
    query_id: object,
    *,
    keep: bool = False,
) -> Iterator[Path]:
    """Create a per-query workspace, deleting it after use unless kept."""
    safe_query_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(query_id))
    if keep:
        workspace = result_root / "_working" / f"qid{safe_query_id}"
        workspace.mkdir(parents=True, exist_ok=True)
        yield workspace
        return

    with TemporaryDirectory(prefix=f"rise_qid{safe_query_id}_") as temp_dir:
        yield Path(temp_dir)
