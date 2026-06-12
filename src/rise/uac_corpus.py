"""Build RISE corpus artifacts and meeting navigation from extracted UAC docs."""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROLE_LABELS = {
    "minutes": "Official minutes",
    "draft_minutes": "Draft minutes",
    "agenda_item": "Agenda items",
    "circulation": "Circulation papers",
    "table_of_contents": "Original table of contents",
    "historical": "Historical documents",
}


def _overview(date: str, grouped: dict[str, list[dict]]) -> str:
    lines = [f"# UAC Meeting: {date}", "", "This file is a navigation object. Read linked source documents for evidence.", ""]
    for role in ("minutes", "draft_minutes", "agenda_item", "circulation", "table_of_contents", "historical"):
        records = grouped.get(role, [])
        if not records:
            continue
        lines.extend([f"## {ROLE_LABELS[role]}", ""])
        for record in sorted(records, key=lambda r: (r.get("item_number") is None, r.get("item_number") or 0, r["doc_id"])):
            title = record.get("title") or record["doc_id"]
            lines.append(f"- {title} | `{record['relpath']}` | doc_id={record['doc_id']}")
        lines.append("")
    return "\n".join(lines)


def build_corpus(records: list[dict], extracted_root: Path, output_root: Path) -> dict:
    """Copy complete docs, generate overviews, Parquet, maps, and manifests."""
    files_root = output_root / "files"
    if files_root.exists():
        shutil.rmtree(files_root)
    files_root.mkdir(parents=True, exist_ok=True)
    good = [dict(record) for record in records if record.get("status") == "ok" and record.get("relpath")]
    documents: dict[str, dict] = {}
    meetings: dict[str, dict[str, list[str]]] = {}
    parquet_rows: list[dict] = []
    relpath_to_docid: dict[str, str] = {}

    grouped_by_date: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for record in good:
        src = extracted_root / record["relpath"]
        dst = files_root / record["relpath"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        record["relpath"] = dst.relative_to(files_root).as_posix()
        documents[record["doc_id"]] = record
        grouped_by_date[record["meeting_date"]][record["role"]].append(record)

    for date, grouped in grouped_by_date.items():
        overview_id = f"meeting_{date.replace('-', '_')}"
        overview_rel = f"meetings/{date}/overview.txt"
        overview_path = files_root / overview_rel
        overview_path.parent.mkdir(parents=True, exist_ok=True)
        overview_path.write_text(_overview(date, grouped), encoding="utf-8")
        overview_record = {
            "doc_id": overview_id,
            "filename": overview_path.name,
            "role": "meeting_overview",
            "meeting_date": date,
            "item_number": None,
            "title": f"UAC Meeting {date}",
            "relpath": overview_rel,
            "status": "ok",
        }
        documents[overview_id] = overview_record
        grouped["meeting_overview"].append(overview_record)
        meetings[date] = {role: [r["doc_id"] for r in values] for role, values in grouped.items()}

    for doc_id, record in documents.items():
        text = (files_root / record["relpath"]).read_text(encoding="utf-8", errors="replace")
        parquet_rows.append({"docid": doc_id, "text": text, "url": record.get("filename", "")})
        relpath_to_docid[record["relpath"]] = doc_id

    output_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(parquet_rows).to_parquet(output_root / "uac_corpus.parquet", index=False)
    (output_root / "document_manifest.json").write_text(json.dumps(documents, indent=2), encoding="utf-8")
    (output_root / "meeting_manifest.json").write_text(json.dumps(meetings, indent=2), encoding="utf-8")
    (output_root / "filename_docid_map.json").write_text(
        json.dumps({"relpath_to_docid": relpath_to_docid}, indent=2), encoding="utf-8"
    )
    report = {
        "source_documents": len(records),
        "successful_source_documents": len(good),
        "failed_source_documents": len(records) - len(good),
        "meeting_overviews": len(meetings),
        "indexed_documents": len(documents),
    }
    (output_root / "completeness_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
