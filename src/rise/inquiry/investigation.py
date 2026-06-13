"""RISE bounded-workspace investigation adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from rise.decompose import make_client, resolve_model
from rise.protocol import for_rise
from rise.rise_agent import run_rise_agent
from rise.run_storage import query_workspace


@dataclass
class InvestigationResult:
    doc_ids: set[str] = field(default_factory=set)
    audit: dict = field(default_factory=dict)


class RiseInvestigator:
    def __init__(
        self,
        *,
        retriever,
        doc_ids: list[str],
        docid_to_relpath: dict[str, str],
        corpus_root: Path,
        result_root: Path,
        related_doc_ids_fn: Callable | None = None,
        max_model_calls: int = 20,
        client=None,
    ):
        self.retriever = retriever
        self.doc_ids = doc_ids
        self.docid_to_relpath = docid_to_relpath
        self.relpath_to_docid = {relpath: doc_id for doc_id, relpath in docid_to_relpath.items()}
        self.corpus_root = Path(corpus_root)
        self.result_root = Path(result_root)
        self.related_doc_ids_fn = related_doc_ids_fn
        self.max_model_calls = max_model_calls
        self.client = client

    def __call__(self, question: str) -> InvestigationResult:
        model = resolve_model()
        config = for_rise(
            agent_model=model,
            bm25_k=500,
            bc_plus_docs=self.corpus_root,
            max_model_calls=self.max_model_calls,
        )
        with query_workspace(self.result_root, "inquiry") as workspace:
            run = run_rise_agent(
                question,
                "inquiry",
                run_config=config,
                searcher=self.retriever,
                doc_ids=self.doc_ids,
                docid_to_relpath=self.docid_to_relpath,
                bc_plus_docs_root=self.corpus_root,
                working_dir=workspace,
                client=self.client or make_client(model),
                map_keys=set(self.relpath_to_docid),
                related_doc_ids_fn=self.related_doc_ids_fn,
                enable_sandbox=False,
            )
        surfaced = {
            self.relpath_to_docid[relpath]
            for relpath in run.surfaced_relpaths
            if relpath in self.relpath_to_docid
        }
        return InvestigationResult(
            surfaced,
            {
                "final_text": run.final_text,
                "queries": run.bm25_queries,
                "read_paths": run.read_paths,
                "tool_calls": run.tool_call_breakdown,
                "elapsed_seconds": run.elapsed_seconds,
                "cost_usd": run.cost_usd,
            },
        )
