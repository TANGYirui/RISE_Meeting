#!/usr/bin/env python3
"""Run RISE on a JSONL query set.

Single agent with three tools (search, bash, read). One conversation,
one trace per query. Compared to run_hierarchical_mini_dev.py this is much
simpler — no orchestrator/sub-agent split, no nested traces.

Per-query output: _traces/qid_<id>/single.json with the full agent trace.
Aggregate output: _summary.json. Judging is decoupled; run scripts/judge.py
afterward to produce _judge_summary.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from rise.api_retry import effective_reasoning_effort
from rise.console import configure_console_stream
from rise.dci_artifacts import PRICE_TABLE, estimate_cost
from rise.decompose import make_client, resolve_model
from rise.retrieval import load_index
from rise.rise_agent import run_rise_agent
from rise.run_storage import default_result_root, query_workspace
from rise.protocol import for_rise
from rise.trajectory import (
    PLACEHOLDER_JUDGE_OUT, PLACEHOLDER_JUDGE_USAGE,
    SCHEMA_VERSION, atomic_write_json, build_per_query_row,
    cached_row_is_reusable, compute_run_config_hash,
)
from rise.uac_workspace import related_doc_ids

DEFAULT_MINI_DEV = REPO_ROOT / "data" / "queries_100.jsonl"
DEFAULT_INDEX = REPO_ROOT / "runs" / "bm25_full"
DEFAULT_MAP = REPO_ROOT / "runs" / "corpus_filename_docid_map.json"
DEFAULT_BC_PLUS_DOCS = REPO_ROOT / "corpus" / "bcp_plus"
DEFAULT_BC_PLUS_DOCS_STRUCTURED = REPO_ROOT / "corpus" / "bcp_plus_structured"


def main() -> None:
    configure_console_stream(sys.stdout)
    configure_console_stream(sys.stderr)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mini-dev", type=Path, default=DEFAULT_MINI_DEV)
    ap.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--filename-map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--bc-plus-docs", type=Path, default=DEFAULT_BC_PLUS_DOCS)
    ap.add_argument("--model", default="mimo-v2.5-pro")
    ap.add_argument("--max-turns", type=int, default=100,
                    help="Aligned with retrieval-agent class (BCP/Pi-Serini default=100). RISE is a retrieval-agent (search+read+bash on mini-corpus), not a direct-corpus-interaction agent like DCI native (which uses 300 per paper §4).")
    ap.add_argument("--bm25-k", type=int, default=1000)
    ap.add_argument("--bm25-top-n-preview", type=int, default=10)
    ap.add_argument("--bm25-snippet-chars", type=int, default=100)
    ap.add_argument("--bash-truncate-chars", type=int, default=4000)
    ap.add_argument("--read-default-limit", type=int, default=2000)
    ap.add_argument("--no-sandbox", action="store_true",
                    help="Disable sandbox-exec on bash (debug only).")
    ap.add_argument("--coerce-final", action="store_true",
                    help="Inject 'commit now' turn at max_turns. "
                         "Default off — paper-faithful, fair comparison. "
                         "Empirically RISE hits this never on dev_100 "
                         "(100/100 natural commit).")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--out-root", type=Path, default=None)
    ap.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Preserve each query's bounded workspace under OUT_ROOT/_working. "
             "By default workspaces use the system temporary directory and "
             "are deleted after each query.",
    )
    # ---- passage mode --------------------------------------------
    ap.add_argument("--passage-mode", action="store_true",
                    help="Switch retrieval and read to passage-level units. "
                         "Requires --passage-index-dir, --passage-files-root, "
                         "--passage-map; --bc-plus-docs is used as the read_doc "
                         "(full-doc) fallback root.")
    ap.add_argument("--passage-index-dir", type=Path,
                    default=REPO_ROOT / "runs" / "bm25_passages_100k")
    ap.add_argument("--passage-files-root", type=Path,
                    default=REPO_ROOT / "corpus" / "bcp_passages_100k_files")
    ap.add_argument("--passage-map", type=Path,
                    default=REPO_ROOT / "runs" / "corpus_filename_passage_map_100k.json")
    # ---- structured-doc mode (doc_representation A/B) ------------
    ap.add_argument("--structured-docs", action="store_true",
                    help="A/B treatment: feed the agent the doc_representation "
                         "pipeline's restructured docs (YAML + TOC + sectioned "
                         "headings) instead of plain text. BM25 index is "
                         "unchanged (still over the original corpus). Switches "
                         "--bc-plus-docs default to bc_plus_docs_restructured "
                         "and swaps in RISE_SYSTEM_PROMPT_STRUCTURED.")
    ap.add_argument("--no-bash", action="store_true",
                    help="Ablation: drop the bash tool. Agent gets only "
                         "search + read — closer to a BCP retrieval-agent "
                         "setup without mini-corpus exploration.")
    ap.add_argument("--document-manifest", type=Path)
    ap.add_argument("--meeting-manifest", type=Path)
    ap.add_argument("--related-doc-cap", type=int, default=20)
    args = ap.parse_args()
    args.model = resolve_model(args.model)

    # Apply structured-docs default override BEFORE we touch args.bc_plus_docs.
    if args.structured_docs and args.bc_plus_docs == DEFAULT_BC_PLUS_DOCS:
        args.bc_plus_docs = DEFAULT_BC_PLUS_DOCS_STRUCTURED

    if args.out_root is None:
        tag = args.model.replace("deepseek-", "")
        if args.passage_mode:
            idx_tag = args.passage_index_dir.name
            args.out_root = default_result_root(
                REPO_ROOT, f"rise_{tag}_t{args.max_turns}_k{args.bm25_k}_{idx_tag}"
            )
        else:
            idx_tag = args.index_dir.name
            struct_tag = "_structured" if args.structured_docs else ""
            nobash_tag = "_nobash" if args.no_bash else ""
            args.out_root = default_result_root(
                REPO_ROOT,
                f"rise_{tag}_t{args.max_turns}_k{args.bm25_k}_{idx_tag}{struct_tag}{nobash_tag}",
            )
    args.out_root = args.out_root.resolve()
    args.out_root.mkdir(parents=True, exist_ok=True)
    reasoning_effort = effective_reasoning_effort()

    # Build the shared RunConfig (unified protocol: max_model_calls,
    # wall_clock_timeout, retry budgets, etc.) and hash it for cache resume.
    run_config = for_rise(
        agent_model=args.model,
        bm25_k=args.bm25_k,
        bm25_top_n_preview=args.bm25_top_n_preview,
        bm25_snippet_chars=args.bm25_snippet_chars,
        bash_truncate_chars=args.bash_truncate_chars,
        read_default_limit=args.read_default_limit,
        enable_sandbox=(not args.no_sandbox),
        index_dir=args.index_dir,
        filename_map=args.filename_map,
        bc_plus_docs=args.bc_plus_docs,
        passage_mode=args.passage_mode,
        passage_index_dir=(args.passage_index_dir if args.passage_mode else ""),
        passage_files_root=(args.passage_files_root if args.passage_mode else ""),
        passage_map=(args.passage_map if args.passage_mode else ""),
        max_model_calls=args.max_turns,
        coerce_final_on_max_turns=bool(args.coerce_final),
        reasoning_effort=reasoning_effort,
        structured_doc_mode=bool(args.structured_docs),
        no_bash=bool(args.no_bash),
    )
    run_config_hash = compute_run_config_hash(run_config.to_hashable_dict())
    print(f"run_config_hash: {run_config_hash}")

    trace_root = (args.out_root / "_traces").resolve()
    per_query_dir = (args.out_root / "_per_query").resolve()
    trace_root.mkdir(parents=True, exist_ok=True)
    per_query_dir.mkdir(parents=True, exist_ok=True)

    if args.passage_mode:
        print(f"loading PASSAGE BM25 index ({args.passage_index_dir}) ...")
        retriever, doc_ids = load_index(args.passage_index_dir)
        print(f"  {len(doc_ids):,} passages")
        print(f"loading passage map ({args.passage_map}) ...")
        pmap = json.loads(args.passage_map.read_text(encoding="utf-8"))
        # passage_id (= bm25 retrieval unit) -> passage relpath
        docid_to_relpath: dict[str, str] = pmap["passage_id_to_relpath"]
        relpath_to_passage_id: dict[str, str] = pmap["relpath_to_passage_id"]
        relpath_to_parent_docid: dict[str, str] = pmap["relpath_to_parent_docid"]
        passage_id_to_parent_docid: dict[str, str] = pmap["passage_id_to_parent_docid"]
        map_keys = set(docid_to_relpath.values())
        print(f"  {len(docid_to_relpath):,} passage_id entries, "
              f"{len(set(passage_id_to_parent_docid.values())):,} parent docs")
    else:
        print("loading BM25 index ...")
        retriever, doc_ids = load_index(args.index_dir)
        print(f"  {len(doc_ids):,} docs")
        print(f"loading filename↔docid map ({args.filename_map}) ...")
        map_blob = json.loads(args.filename_map.read_text(encoding="utf-8"))
        relpath_to_docid: dict[str, str] = map_blob["relpath_to_docid"]
        docid_to_relpath: dict[str, str] = {v: k for k, v in relpath_to_docid.items()}
        map_keys = set(relpath_to_docid.keys())
        relpath_to_parent_docid = relpath_to_docid  # alias for coverage
        passage_id_to_parent_docid = {}
        print(f"  {len(relpath_to_docid):,} entries")

    records = [
        json.loads(l) for l in args.mini_dev.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    related_fn = None
    if args.document_manifest and args.meeting_manifest:
        document_manifest = json.loads(args.document_manifest.read_text(encoding="utf-8"))
        meeting_manifest = json.loads(args.meeting_manifest.read_text(encoding="utf-8"))
        related_fn = lambda hits: related_doc_ids(
            hits, document_manifest, meeting_manifest, cap=args.related_doc_cap
        )
    print(f"running RISE on {len(records)} queries")
    print(f"  model={args.model}  (judge: decoupled — run scripts/judge.py after)")
    print(f"  max_turns={args.max_turns}  bm25_k={args.bm25_k}  bash_truncate={args.bash_truncate_chars}")
    print(f"  sandbox={'off' if args.no_sandbox else 'on'}  c={args.concurrency}")
    print(f"  passage_mode={'YES' if args.passage_mode else 'no'}")
    if args.passage_mode:
        print(f"  passage_files_root={args.passage_files_root}")
        print(f"  parent_docs_root (read_doc fallback)={args.bc_plus_docs}")
    print(f"  out_root={args.out_root}")
    print(f"  workspace={'preserved under out_root/_working' if args.keep_workspace else 'temporary; deleted after each query'}")
    print()

    # Route credentials by model: gpt-5*/o-series → OpenAI direct,
    # mimo-* → Xiaomi, deepseek-* → DeepSeek.
    agent_client = make_client(args.model)
    bc_plus_docs_root = args.bc_plus_docs.resolve()
    # In passage mode, the bm25-search tool hardlinks from passage_files_root,
    # and `read_doc` reads from bc_plus_docs_root (full corpus).
    search_root = args.passage_files_root.resolve() if args.passage_mode else bc_plus_docs_root

    print_lock = threading.Lock()
    header = f"{'qid':>5}  {'turns':>5}  {'srch':>4}  {'queries':>7}  {'bash':>4}  {'read':>4}  {'covA':>4}  {'covM':>5}  {'cost':>8}  expected -> final_text"
    print(header, flush=True)
    print("-" * len(header), flush=True)

    def _process(rec: dict) -> dict:
        qid = rec["query_id"]
        per_query_path = per_query_dir / f"qid_{qid}.json"
        if per_query_path.exists():
            try:
                cached = json.loads(per_query_path.read_text(encoding="utf-8"))
            except Exception:
                cached = None
            if cached is not None:
                ok, reason = cached_row_is_reusable(
                    cached,
                    expected_runner="rise",
                    expected_model=args.model,
                    expected_run_config_hash=run_config_hash,
                )
                if ok:
                    return cached
                print(f"qid={qid} cache invalid ({reason}); re-running", flush=True)
        trace_path = trace_root / f"qid_{qid}" / "single.json"
        with query_workspace(args.out_root, qid, keep=args.keep_workspace) as working_dir:
            run = run_rise_agent(
                question=rec["query"], query_id=qid,
                run_config=run_config,
                searcher=retriever, doc_ids=doc_ids,
                docid_to_relpath=docid_to_relpath,
                bc_plus_docs_root=search_root,
                working_dir=working_dir,
                client=agent_client,
                trace_path=trace_path,
                map_keys=map_keys,
                enable_sandbox=(not args.no_sandbox),
                parent_docs_root=bc_plus_docs_root if args.passage_mode else None,
                relpath_to_parent_docid=relpath_to_parent_docid if args.passage_mode else None,
                related_doc_ids_fn=related_fn,
            )

        # Cost: agent only. Judge is decoupled — `scripts/judge.py` reads
        # this row's `final_text` + `gold_answer` later and atomically
        # overwrites the placeholder `judge`/`judge_usage`/`judge_cost_usd`
        # / `total_cost_usd` / `is_correct` fields.
        agent_cost = run.cost_usd
        judge_out = dict(PLACEHOLDER_JUDGE_OUT)
        judge_usage = dict(PLACEHOLDER_JUDGE_USAGE)
        judge_cost = 0.0

        # Coverage based on surfaced relpaths from bash/read/bm25_search.
        # In passage mode: surfaced_relpaths contain PASSAGE relpaths
        # (e.g. `<domain>/<title>/passages/p0042.txt`); the
        # relpath_to_parent_docid map keys are PARENT relpaths
        # (`<domain>/<title>.txt`). We coerce passage→parent first then
        # intersect against doc-level gold/evidence sets. In doc mode the
        # surfaced relpaths already match the map keys, so coercion is a
        # no-op.
        import re as _re
        _passage_strip = _re.compile(r"^(.+?)/passages/p\d+\.txt$")

        def _to_parent_relpath(p: str) -> str:
            m = _passage_strip.match(p)
            return (m.group(1) + ".txt") if m else p

        gold = set(rec.get("gold_doc_ids", []))
        evi = set(rec.get("evidence_doc_ids", []))
        surfaced_docids = {
            relpath_to_parent_docid[_to_parent_relpath(p)]
            for p in run.surfaced_relpaths
            if _to_parent_relpath(p) in relpath_to_parent_docid
        }
        row = build_per_query_row(
            run_config=run_config, run_config_hash=run_config_hash,
            query_id=qid, question=rec["query"], gold_answer=rec["answer"],
            gold_doc_ids=list(gold), evidence_doc_ids=list(evi),
            final_text=run.final_text,
            judge_out=judge_out,
            judge_usage=judge_usage, judge_cost_usd=judge_cost,
            terminated_by=run.terminated_by, elapsed_seconds=run.elapsed_seconds,
            n_turns=run.n_turns, n_attempts=1,
            agent_usage={
                "input_tokens": run.input_tokens,
                "cached_input_tokens": run.cached_input_tokens,
                "output_tokens": run.output_tokens,
                "reasoning_tokens": run.reasoning_tokens,
            },
            agent_cost_usd=agent_cost,
            surfaced_relpaths=run.surfaced_relpaths,
            surfaced_docids=surfaced_docids,
            all_retrieved=sorted(surfaced_docids),
            tool_usage=dict(run.tool_call_breakdown),
            runner_specific={
                "n_bm25_searches": run.n_bm25_searches,
                "n_bm25_queries": run.n_bm25_queries,
                "n_read_passage_calls": run.n_read_passage_calls,
                "n_read_doc_calls": run.n_read_doc_calls,
                "bash_kinds": run.bash_kinds,
                "bm25_queries": run.bm25_queries,
                "read_paths": run.read_paths,
            },
            trace_path=str(trace_path.relative_to(args.out_root)),
        )
        atomic_write_json(per_query_path, row)
        return row

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        future_to_rec = {ex.submit(_process, rec): rec for rec in records}
        for fut in as_completed(future_to_rec):
            rec = future_to_rec[fut]
            try:
                row = fut.result()
            except Exception as e:
                with print_lock:
                    print(f"qid={rec['query_id']} FAILED: {type(e).__name__}: {str(e)[:200]}", flush=True)
                continue
            results.append(row)
            with print_lock:
                tu = row.get("tool_usage") or {}
                rs = row.get("runner_specific") or {}
                # No `corr` column — judge is decoupled; row contains
                # placeholder judge fields until scripts/judge.py runs.
                print(
                    f"{row['query_id']:>5}  {row['n_turns']:>5}  "
                    f"{rs.get('n_bm25_searches', 0):>4}  {rs.get('n_bm25_queries', 0):>7}  "
                    f"{tu.get('bash', 0):>4}  {tu.get('read', 0):>4}  "
                    f"{row['coverage_any']*100:>3.0f}  {row['coverage_mean']*100:>4.1f}  "
                    f"${row['agent_cost_usd']:>7.4f}  "
                    f"{str(row['gold_answer'])[:30]} -> {str(row['final_text'])[:35].splitlines()[0] if row['final_text'] else ''}",
                    flush=True,
                )

    results.sort(key=lambda r: int(r["query_id"]) if str(r["query_id"]).isdigit() else 0)
    n = len(results)
    # accuracy is judge-deferred — see `scripts/judge.py` and `_judged_summary.json`.
    judge_pending = all((r.get("judge") or {}).get("reasoning", "") == "" for r in results)

    summary = {
        "config": {
            "model": args.model,
            "max_turns": args.max_turns,
            "bm25_k": args.bm25_k,
            "bm25_top_n_preview": args.bm25_top_n_preview,
            "bm25_snippet_chars": args.bm25_snippet_chars,
            "bash_truncate_chars": args.bash_truncate_chars,
            "read_default_limit": args.read_default_limit,
            "enable_sandbox": (not args.no_sandbox),
            "concurrency": args.concurrency,
            "price_table": PRICE_TABLE.get(args.model, {}),
        },
        "aggregate": {
            "n": n,
            "judge_pending": judge_pending,
            "mean_n_turns": mean(r["n_turns"] for r in results) if n else 0,
            # Aggregates read from the unified row's tool_usage + runner_specific.
            # RISE-specific counts live in runner_specific; tool calls in tool_usage.
            "mean_n_bm25_searches": mean((r.get("runner_specific") or {}).get("n_bm25_searches", 0) for r in results) if n else 0,
            "mean_n_bm25_queries": mean((r.get("runner_specific") or {}).get("n_bm25_queries", 0) for r in results) if n else 0,
            "mean_n_bash_calls": mean((r.get("tool_usage") or {}).get("bash", 0) for r in results) if n else 0,
            "mean_n_read_calls": mean((r.get("tool_usage") or {}).get("read", 0) for r in results) if n else 0,
            "mean_n_read_passage_calls": mean((r.get("runner_specific") or {}).get("n_read_passage_calls", 0) for r in results) if n else 0,
            "mean_n_read_doc_calls": mean((r.get("runner_specific") or {}).get("n_read_doc_calls", 0) for r in results) if n else 0,
            "passage_only_qid_rate": (
                sum(1 for r in results if (r.get("runner_specific") or {}).get("n_read_doc_calls", 0) == 0 and (r.get("runner_specific") or {}).get("n_read_passage_calls", 0) > 0) / n
            ) if n else 0,
            # Commit-type breakdown: how the agent ended.
            # `done` = model emitted final answer naturally (no tool call in last turn)
            # `coerced_max_turns` / `wall_clock_timeout` = ran out of budget, coerce step injected
            # `coerce_failed` = even the coerce step couldn't produce final text
            # `no_final` = empty final_text (any reason)
            "n_committed_natural": sum(1 for r in results if (r.get("terminated_by") or "").split(":")[0].strip() == "done"),
            "n_committed_coerced": sum(1 for r in results if "coerced_max_turns" in (r.get("terminated_by") or "") or "wall_clock_timeout" in (r.get("terminated_by") or "")),
            "n_no_final": sum(1 for r in results if not (r.get("final_text", "") or "").strip()),
            "mean_coverage_any": mean(r["coverage_any"] for r in results) if n else 0,
            "mean_coverage_mean": mean(r["coverage_mean"] for r in results) if n else 0,
            "mean_coverage_all": mean(r["coverage_all"] for r in results) if n else 0,
            "mean_evidence_coverage_mean": mean(r["evidence_coverage_mean"] for r in results) if n else 0,
            "mean_n_surfaced": mean(r["n_surfaced"] for r in results) if n else 0,
            "total_agent_cost_usd": sum(r["agent_cost_usd"] for r in results),
            "mean_agent_cost_per_query_usd": (sum(r["agent_cost_usd"] for r in results) / n) if n else 0,
            "mean_elapsed_seconds": mean(r["elapsed_seconds"] for r in results) if n else 0,
        },
        "per_query": results,
    }
    out_path = args.out_root / "_summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    a = summary["aggregate"]
    print()
    print(f"(judge pending — run: scripts/judge.py --run-dir {args.out_root} --judge-model <MODEL>)")
    print(f"n: {a['n']}  mean turns: {a['mean_n_turns']:.1f}")
    print(f"mean search-calls / total queries / bash / read:  {a['mean_n_bm25_searches']:.1f} / {a['mean_n_bm25_queries']:.1f} / {a['mean_n_bash_calls']:.1f} / {a['mean_n_read_calls']:.1f}")
    if args.passage_mode:
        print(f"  passage-mode read split:  read_passage={a['mean_n_read_passage_calls']:.1f}  read_doc={a['mean_n_read_doc_calls']:.1f}  passage_only_qids={a['passage_only_qid_rate']*100:.1f}%")
    print(f"commit: natural={a['n_committed_natural']}/{a['n']}, coerced={a['n_committed_coerced']}/{a['n']}, no_final={a['n_no_final']}/{a['n']}")
    print(f"mean covA / covM:   {a['mean_coverage_any']*100:.1f} / {a['mean_coverage_mean']*100:.1f}")
    print(f"agent cost total / mean: ${a['total_agent_cost_usd']:.4f} / ${a['mean_agent_cost_per_query_usd']:.4f}")
    print(f"\nwrote -> {out_path}")


if __name__ == "__main__":
    main()
