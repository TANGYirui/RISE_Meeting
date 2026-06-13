"""High-recall candidate discovery over BM25 and complete source text."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping


@dataclass
class DiscoveryResult:
    doc_ids: set[str] = field(default_factory=set)
    scores: dict[str, float] = field(default_factory=dict)
    sources: dict[str, list[str]] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)


def discover_candidates(
    queries: Iterable[str],
    exact_terms: Iterable[str],
    retrieve_fn: Callable[[str, int], list[tuple[str, float]]],
    document_manifest: Mapping[str, dict],
    corpus_root: Path,
    *,
    depth: int = 1000,
) -> DiscoveryResult:
    result = DiscoveryResult(queries=list(dict.fromkeys(q for q in queries if q.strip())))
    for query in result.queries:
        for doc_id, score in retrieve_fn(query, depth):
            result.doc_ids.add(doc_id)
            result.scores[doc_id] = max(score, result.scores.get(doc_id, float("-inf")))
            result.sources.setdefault(doc_id, []).append(f"bm25:{query}")
    for term in dict.fromkeys(value for value in exact_terms if value.strip()):
        needle = term.casefold()
        for doc_id, record in document_manifest.items():
            relpath = record.get("relpath")
            if not relpath:
                continue
            path = corpus_root / relpath
            if path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace").casefold():
                result.doc_ids.add(doc_id)
                result.sources.setdefault(doc_id, []).append(f"exact_scan:{term}")
                result.scores.setdefault(doc_id, 0.0)
    return result

