"""Materialize the restructured BCP corpus as a parallel `bc_plus_docs` tree.

Read each (relpath, docid) pair from corpus_filename_docid_map.json, look up the
restructured_text for that docid in our full-corpus parquet, and write it to
`bc_plus_docs_restructured/<relpath>` (same directory structure as the original
corpus, so RISE can use it via `--bc-plus-docs` without any other code changes).

Run once before any A/B experiment. Idempotent: re-running overwrites files,
so it's safe to re-execute if the parquet is regenerated.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # repo root (works on any host)
CORPUS_DIR_ORIG = ROOT / "corpus" / "bcp_plus"
CORPUS_DIR_OUT  = ROOT / "corpus" / "bcp_plus_structured"
MAP_FILE = ROOT / "outputs/corpus_filename_docid_map.json"
PARQUET  = ROOT / "doc_representation/outputs/full_corpus_5p4/data.parquet"


def main() -> None:
    print(f"Loading filename map …")
    m = json.loads(MAP_FILE.read_text())
    relpath_to_docid: dict[str, str] = m["relpath_to_docid"]
    print(f"  {len(relpath_to_docid):,} relpath → docid entries")

    print(f"Loading restructured corpus parquet ({PARQUET.stat().st_size/1e9:.2f} GB) …")
    df = pd.read_parquet(PARQUET, columns=["docid", "restructured_text"])
    df["docid"] = df["docid"].astype(str)
    docid_to_text: dict[str, str] = dict(zip(df["docid"], df["restructured_text"]))
    print(f"  {len(docid_to_text):,} docid → restructured_text entries")

    CORPUS_DIR_OUT.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {CORPUS_DIR_OUT} …")

    t0 = time.time()
    n_written = 0
    n_missing_text = 0
    n_empty_text = 0
    total_bytes = 0
    last_report = 0
    for relpath, docid in relpath_to_docid.items():
        text = docid_to_text.get(str(docid))
        if text is None:
            n_missing_text += 1
            continue
        if not text:
            n_empty_text += 1
            continue
        dest = CORPUS_DIR_OUT / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Use byte-level write to be safe with weird Unicode in restructured text.
        dest.write_text(text, encoding="utf-8")
        n_written += 1
        total_bytes += len(text)
        # Periodic progress (every 5000 files)
        if n_written - last_report >= 5000:
            elapsed = time.time() - t0
            rate = n_written / max(0.1, elapsed)
            print(f"  {n_written:>6,} / {len(relpath_to_docid):,}  ({rate:.0f}/s, {total_bytes/1e9:.2f} GB)")
            last_report = n_written

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s.")
    print(f"  written:        {n_written:,}")
    print(f"  missing text:   {n_missing_text:,}")
    print(f"  empty text:     {n_empty_text:,}")
    print(f"  total bytes:    {total_bytes/1e9:.2f} GB")
    print(f"  corpus tree:    {CORPUS_DIR_OUT}")


if __name__ == "__main__":
    main()
