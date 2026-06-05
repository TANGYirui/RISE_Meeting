"""Run the full 100k BCP corpus through gpt-5.4-nano (batch, low effort).

Multi-stage, resumable. Each stage saves state to state.json so the script
can be killed and re-run without losing progress / paying twice.

Stages (run sequentially, each idempotent):
  A. pack:    split 100k docs into N batch input JSONL files (capped by size + req count)
  B. submit:  upload each input file and create OpenAI batch jobs
  C. poll:    wait until all batches reach a terminal state
  D. process: download each output file, run validate_and_locate + build_final
              per doc, write per-doc .md + a single audit.jsonl
  E. parquet: roll everything into a single HF-ready parquet

Usage:
    uv run python doc_representation/scripts/run_full_corpus.py [stages]
    # default `stages` is "pack,submit,poll,process,parquet"

Outputs:
    outputs/full_corpus_5p4/state.json
    outputs/full_corpus_5p4/batches/batch_NN_input.jsonl
    outputs/full_corpus_5p4/batches/batch_NN_output.jsonl
    outputs/full_corpus_5p4/docs/<docid_prefix2>/<docid>.md
    outputs/full_corpus_5p4/audit.jsonl
    outputs/full_corpus_5p4/data.parquet
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = ROOT / "doc_representation"
CORPUS = ROOT / "external/dci-agent-lite/corpus/browsecomp_plus/data.parquet"

OUT_DIR = EXP_DIR / "outputs" / "full_corpus_5p4"
OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "batches").mkdir(exist_ok=True)
(OUT_DIR / "docs").mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP_DIR / "scripts"))
load_dotenv(ROOT / ".env")

from section_one_doc import (  # noqa: E402
    SECTION_PROMPT,
    build_final,
    truncate_for_llm,
    validate_and_locate,
)

MODEL = "gpt-5.4-nano"
EFFORT = "low"
STATE_PATH = OUT_DIR / "state.json"

# Batch packing limits (with safety margin)
MAX_BATCH_BYTES = 180 * 1024 * 1024  # 180 MB (OpenAI cap is 200 MB)
MAX_BATCH_REQS  = 5_000               # OpenAI cap is 50k, but 5k keeps batches snappy

# Pricing (per 1M tokens) — gpt-5.4-nano batch (50% off std $0.20/$0.02/$1.25)
PRICING = {"input": 0.10, "cached": 0.01, "output": 0.625}

client = OpenAI(
    api_key=os.environ["OPENAI_DIRECT_API_KEY"],
    base_url="https://api.openai.com/v1",
)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"batches": [], "stage": "init"}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def build_request_line(docid: str, doc_text: str) -> tuple[dict, dict]:
    llm_input, trunc_info = truncate_for_llm(doc_text)
    prompt = SECTION_PROMPT.replace("<<<DOC>>>", llm_input)
    req = {
        "custom_id": str(docid),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 32768,
            "reasoning_effort": EFFORT,
        },
    }
    return req, trunc_info


def stage_pack(state: dict) -> dict:
    """Build all batch input JSONL files. Idempotent — skips if files exist."""
    if state.get("batches"):
        print(f"[pack] state already has {len(state['batches'])} batches; skipping pack")
        return state

    df = pd.read_parquet(CORPUS, columns=["docid", "text", "url"])
    print(f"[pack] loaded {len(df):,} docs")

    # Sort by text length so each batch is somewhat homogeneous (avoids one huge
    # 471k doc dominating a small batch). Not strictly needed but nicer.
    df = df.assign(_n=df["text"].str.len()).sort_values("_n").reset_index(drop=True)

    batches: list[dict] = []
    cur_path: Path | None = None
    cur_fp = None
    cur_bytes = 0
    cur_count = 0
    cur_docids: list[str] = []
    batch_idx = 0
    trunc_records: dict[str, dict] = {}

    def open_new():
        nonlocal cur_path, cur_fp, cur_bytes, cur_count, cur_docids, batch_idx
        if cur_fp is not None:
            cur_fp.close()
            batches.append({
                "idx": batch_idx, "path": str(cur_path),
                "n_requests": cur_count, "n_bytes": cur_bytes,
                "docids": cur_docids,
                "batch_id": None, "status": "pending",
            })
            batch_idx += 1
        cur_path = OUT_DIR / "batches" / f"batch_{batch_idx:02d}_input.jsonl"
        cur_fp = open(cur_path, "w")
        cur_bytes = 0; cur_count = 0; cur_docids = []

    open_new()
    for r in df.itertuples():
        req, trunc = build_request_line(r.docid, r.text)
        line = json.dumps(req) + "\n"
        line_bytes = len(line.encode())
        if cur_count >= MAX_BATCH_REQS or (cur_bytes + line_bytes) > MAX_BATCH_BYTES:
            open_new()
        cur_fp.write(line)
        cur_bytes += line_bytes
        cur_count += 1
        cur_docids.append(str(r.docid))
        if trunc.get("truncated"):
            trunc_records[str(r.docid)] = trunc

    # close last
    if cur_fp is not None:
        cur_fp.close()
        batches.append({
            "idx": batch_idx, "path": str(cur_path),
            "n_requests": cur_count, "n_bytes": cur_bytes,
            "docids": cur_docids,
            "batch_id": None, "status": "pending",
        })

    state["batches"] = batches
    state["truncations"] = trunc_records
    state["stage"] = "packed"
    state["packed_at"] = int(time.time())
    save_state(state)
    print(f"[pack] wrote {len(batches)} batch files")
    for b in batches:
        print(f"  batch_{b['idx']:02d}: {b['n_requests']:>4} reqs, {b['n_bytes']/1e6:.1f} MB")
    print(f"[pack] truncations: {len(trunc_records)} docs")
    return state


def stage_submit(state: dict) -> dict:
    """Submit each batch that hasn't been submitted yet."""
    pending = [b for b in state["batches"] if b["batch_id"] is None]
    if not pending:
        print(f"[submit] all {len(state['batches'])} batches already submitted")
        return state
    print(f"[submit] {len(pending)} batches to submit")
    for b in pending:
        path = Path(b["path"])
        print(f"  uploading {path.name} ({b['n_bytes']/1e6:.1f} MB) …", end=" ", flush=True)
        with open(path, "rb") as fp:
            f = client.files.create(file=fp, purpose="batch")
        bj = client.batches.create(
            input_file_id=f.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={
                "purpose": "BCP doc_representation full-corpus 5.4-nano-low",
                "batch_idx": str(b["idx"]),
            },
        )
        b["file_id"] = f.id
        b["batch_id"] = bj.id
        b["status"] = bj.status
        b["submitted_at"] = int(time.time())
        save_state(state)  # save after each successful create
        print(f"file={f.id}  batch={bj.id}  status={bj.status}")
    state["stage"] = "submitted"
    save_state(state)
    return state


def stage_poll(state: dict, poll_interval: int = 30) -> dict:
    """Poll all in-flight batches until terminal status."""
    terminal = {"completed", "failed", "expired", "cancelled"}
    print(f"[poll] {len(state['batches'])} batches, polling every {poll_interval}s")
    t0 = time.time()
    while True:
        all_done = True
        # Refresh status for non-terminal batches
        statuses: dict[str, int] = {}
        completed_total = 0; total_requests = 0
        for b in state["batches"]:
            if b["status"] in terminal:
                statuses[b["status"]] = statuses.get(b["status"], 0) + 1
                total_requests += b["n_requests"]
                completed_total += b.get("completed_count", b["n_requests"] if b["status"] == "completed" else 0)
                continue
            bj = client.batches.retrieve(b["batch_id"])
            b["status"] = bj.status
            rc = bj.request_counts
            b["completed_count"] = rc.completed
            b["failed_count"]    = rc.failed
            b["output_file_id"]  = bj.output_file_id
            b["error_file_id"]   = bj.error_file_id
            statuses[bj.status] = statuses.get(bj.status, 0) + 1
            total_requests += b["n_requests"]
            completed_total += rc.completed
            if bj.status not in terminal:
                all_done = False
        save_state(state)
        elapsed = int(time.time() - t0)
        print(f"  [{elapsed:>5}s] {dict(sorted(statuses.items()))}   completed={completed_total}/{total_requests}", flush=True)
        if all_done:
            break
        time.sleep(poll_interval)
    state["stage"] = "polled"
    save_state(state)
    return state


def _last_section_span_pct(final_text: str) -> float:
    lines = final_text.splitlines()
    in_toc = False; last = None
    for ln in lines:
        if ln.strip() == "## Table of Contents":
            in_toc = True; continue
        if in_toc:
            if ln.startswith("- L"):
                try:
                    rng = ln[3:].split(":", 1)[0]
                    a, b = rng.split("–")
                    last = (int(a), int(b))
                except Exception: pass
            elif ln.startswith("## "): break
    if not last or not lines: return 0.0
    return (last[1] - last[0] + 1) / len(lines)


def _process_one(r: dict, doc: dict, batch_idx: int, audit_fp, accum: dict) -> None:
    """Process one batch result line. Writes one audit JSON row + per-doc .md.
    Updates `accum` dict with running totals: cost_total, tail_bloat, empty_counts."""
    did = r["custom_id"]
    body = r["response"]["body"]
    content = (body["choices"][0]["message"].get("content") or "").strip()
    usage = body["usage"]
    in_tok = usage["prompt_tokens"]
    out_tok = usage["completion_tokens"]
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    reason = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

    try:
        data = json.loads(content)
        sections = data.get("sections", []) if isinstance(data, dict) else []
        parse_err = None
    except json.JSONDecodeError as e:
        sections = []
        parse_err = str(e)

    located, skipped, warnings = validate_and_locate(doc["text"], sections)
    empty_reason = None
    if not located:
        if parse_err: empty_reason = "llm-empty"
        elif not sections: empty_reason = "llm-zero"
        else: empty_reason = "all-failed"

    final = build_final(doc["text"], located, empty_reason=empty_reason)
    tail_pct = _last_section_span_pct(final)

    # Sharded output: docs/<first2>/<docid>.md
    shard = (did[:2] if len(did) >= 2 else "00").lower()
    md_dir = OUT_DIR / "docs" / shard
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / f"{did}.md").write_text(final)

    uncached = max(0, in_tok - cached)
    cost = (uncached * PRICING["input"] + cached * PRICING["cached"] + out_tok * PRICING["output"]) / 1_000_000
    accum["cost_total"] = accum.get("cost_total", 0.0) + cost
    if empty_reason:
        accum["empty"][empty_reason] = accum["empty"].get(empty_reason, 0) + 1
    if tail_pct >= 0.40 and len(located) > 1:
        accum["tail_bloat"] = accum.get("tail_bloat", 0) + 1

    audit_fp.write(json.dumps({
        "docid": did, "url": doc["url"], "batch_idx": batch_idx,
        "model": MODEL, "effort": EFFORT,
        "doc_chars": len(doc["text"]),
        "located_count": len(located),
        "skipped_count": len(skipped),
        "warning_count": len(warnings),
        "empty_reason": empty_reason,
        "last_section_pct": round(tail_pct * 100, 1),
        "in_tok": in_tok, "out_tok": out_tok, "reason_tok": reason, "cached": cached,
        "cost_usd": round(cost, 6),
        "strategies": sorted(set(s["strategy"] for s in located)),
        "parse_error": parse_err,
    }, ensure_ascii=False) + "\n")


def stage_process(state: dict) -> dict:
    """Download output files, process each doc, write per-doc .md + audit.jsonl.
    Per-doc errors are caught and recorded; one bad doc never aborts a batch."""
    df = pd.read_parquet(CORPUS, columns=["docid", "text", "url"])
    docid_to_doc = {str(r["docid"]): {"docid": str(r["docid"]), "text": r["text"], "url": r["url"]} for _, r in df.iterrows()}

    audit_path = OUT_DIR / "audit.jsonl"
    audit_fp = open(audit_path, "w")
    accum: dict = {"cost_total": 0.0, "empty": {}, "tail_bloat": 0}
    n_total = 0
    n_proc_errors = 0
    n_api_errors = 0

    for b in state["batches"]:
        if b["status"] != "completed":
            print(f"  skip batch_{b['idx']:02d} (status={b['status']})")
            continue
        out_path = OUT_DIR / "batches" / f"batch_{b['idx']:02d}_output.jsonl"
        if not out_path.exists():
            print(f"  downloading batch_{b['idx']:02d} output …", flush=True)
            raw = client.files.content(b["output_file_id"]).text
            out_path.write_text(raw)
        else:
            raw = out_path.read_text()
        n_in_batch = 0
        n_batch_errors = 0
        for line in raw.strip().splitlines():
            try:
                r = json.loads(line)
            except Exception as e:
                audit_fp.write(json.dumps({"batch_idx": b["idx"], "json_error": repr(e)}) + "\n")
                n_batch_errors += 1
                continue
            did = r.get("custom_id")
            doc = docid_to_doc.get(did)
            if doc is None:
                continue
            if r.get("error"):
                audit_fp.write(json.dumps({"docid": did, "batch_idx": b["idx"], "error": r["error"]}) + "\n")
                n_api_errors += 1
                continue
            try:
                _process_one(r, doc, b["idx"], audit_fp, accum)
                n_in_batch += 1
                n_total += 1
            except Exception as e:
                n_proc_errors += 1; n_batch_errors += 1
                audit_fp.write(json.dumps({
                    "docid": did, "batch_idx": b["idx"],
                    "processing_error": repr(e),
                }) + "\n")
        print(f"  batch_{b['idx']:02d}: processed {n_in_batch} docs"
              + (f" ({n_batch_errors} errors)" if n_batch_errors else ""))
    audit_fp.close()
    state["stage"] = "processed"
    state["totals"] = {
        "n_docs_processed": n_total,
        "total_cost_usd": round(accum["cost_total"], 4),
        "empty_counts": accum["empty"],
        "tail_bloat_count": accum["tail_bloat"],
        "processing_errors": n_proc_errors,
        "api_errors": n_api_errors,
    }
    save_state(state)
    print()
    print(f"[process] {n_total} docs processed")
    print(f"  total cost:        ${accum['cost_total']:.4f}")
    print(f"  empty:             {accum['empty']}")
    print(f"  tail-bloat:        {accum['tail_bloat']}/{n_total}")
    print(f"  api errors:        {n_api_errors}")
    print(f"  processing errors: {n_proc_errors}")
    return state


def stage_parquet(state: dict) -> dict:
    """Aggregate per-doc .md + audit.jsonl into one HF-ready parquet."""
    print(f"[parquet] loading corpus + audit …")
    df_corp = pd.read_parquet(CORPUS, columns=["docid", "text", "url"])
    df_corp["docid"] = df_corp["docid"].astype(str)

    audit_rows = []
    audit_path = OUT_DIR / "audit.jsonl"
    if audit_path.exists():
        with open(audit_path) as f:
            for line in f:
                try:
                    audit_rows.append(json.loads(line))
                except: pass
    df_aud = pd.DataFrame(audit_rows)
    print(f"[parquet] audit rows: {len(df_aud):,}")

    # Read per-doc .md into a column
    md_texts = []
    for did in df_corp["docid"]:
        shard = (did[:2] if len(did) >= 2 else "00").lower()
        md = OUT_DIR / "docs" / shard / f"{did}.md"
        md_texts.append(md.read_text() if md.exists() else None)
    df_corp["restructured_text"] = md_texts

    # Join audit
    if len(df_aud):
        # keep only the columns we want
        keep = ["docid", "located_count", "skipped_count", "warning_count",
                "empty_reason", "last_section_pct", "in_tok", "out_tok",
                "reason_tok", "cost_usd", "strategies", "doc_chars"]
        df_aud = df_aud[[c for c in keep if c in df_aud.columns]]
        df_aud["docid"] = df_aud["docid"].astype(str)
        df_corp = df_corp.merge(df_aud, on="docid", how="left")

    out = OUT_DIR / "data.parquet"
    df_corp.to_parquet(out, index=False)
    print(f"[parquet] wrote {out}  ({out.stat().st_size/1e6:.1f} MB, {len(df_corp):,} rows)")
    print(f"  columns: {list(df_corp.columns)}")
    print(f"  docs with restructured_text: {df_corp['restructured_text'].notna().sum():,}")
    return state


STAGES = {
    "pack":    stage_pack,
    "submit":  stage_submit,
    "poll":    stage_poll,
    "process": stage_process,
    "parquet": stage_parquet,
}


def main(stages: list[str]) -> None:
    state = load_state()
    print(f"=== run_full_corpus  stages={stages}  stage in state={state.get('stage')} ===")
    for s in stages:
        if s not in STAGES:
            raise SystemExit(f"unknown stage: {s}")
        print(f"\n--- stage: {s} ---")
        state = STAGES[s](state)


if __name__ == "__main__":
    stages = sys.argv[1].split(",") if len(sys.argv) > 1 else ["pack", "submit", "poll", "process", "parquet"]
    main(stages)
