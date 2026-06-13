#!/usr/bin/env python3
"""Evaluate saved structured Inquiry JSON records against a local JSONL gold set."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rise.inquiry.evaluation import evaluate_inquiry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--inquiries", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    gold = {
        row["inquiry_id"]: row
        for line in args.gold.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }
    inquiries = json.loads(args.inquiries.read_text(encoding="utf-8"))
    records = inquiries if isinstance(inquiries, list) else [inquiries]
    results = []
    for inquiry in records:
        expected = gold.get(inquiry["inquiry_id"], {})
        results.append(
            {
                "inquiry_id": inquiry["inquiry_id"],
                **evaluate_inquiry(
                    confirmed_topic_ids=[topic["topic_id"] for topic in inquiry.get("confirmed_topics", [])],
                    possible_topic_ids=[topic["topic_id"] for topic in inquiry.get("possible_topics", [])],
                    minutes_doc_ids=[
                        source["doc_id"]
                        for topic in inquiry.get("confirmed_topics", []) + inquiry.get("possible_topics", [])
                        for source in topic.get("minutes_documents", [])
                    ],
                    gold_topic_ids=expected.get("topic_ids", []),
                    gold_minutes_doc_ids=expected.get("minutes_doc_ids", []),
                ),
            }
        )
    output = json.dumps(results, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
