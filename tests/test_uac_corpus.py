import json
from pathlib import Path

from rise.uac_corpus import build_corpus


def _record(doc_id, role, date, relpath, title="", item_number=None):
    return {
        "doc_id": doc_id,
        "filename": f"{doc_id}.pdf",
        "role": role,
        "meeting_date": date,
        "item_number": item_number,
        "title": title,
        "relpath": relpath,
        "status": "ok",
    }


def test_build_corpus_groups_meeting_and_distinguishes_minutes(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    records = [
        _record("minutes_240509", "minutes", "2024-05-09", "minutes.txt"),
        _record("item1_draft", "draft_minutes", "2024-05-09", "draft.txt", item_number=1),
        _record("item5_net_zero", "agenda_item", "2024-05-09", "item5.txt", "Net Zero", 5),
        _record("toc_20240509", "table_of_contents", "2024-05-09", "toc.txt"),
    ]
    for record in records:
        (docs / record["relpath"]).write_text(record["doc_id"], encoding="utf-8")

    report = build_corpus(records, docs, tmp_path / "out")
    manifest = json.loads((tmp_path / "out" / "meeting_manifest.json").read_text())
    overview = (tmp_path / "out" / "files" / "meetings" / "2024-05-09" / "overview.txt").read_text()

    assert report["source_documents"] == 4
    assert report["indexed_documents"] == 5
    assert manifest["2024-05-09"]["minutes"] == ["minutes_240509"]
    assert manifest["2024-05-09"]["draft_minutes"] == ["item1_draft"]
    assert "Official minutes" in overview
    assert "Draft minutes" in overview


def test_build_corpus_removes_stale_files_from_previous_build(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "minutes.txt").write_text("official minutes", encoding="utf-8")
    out = tmp_path / "out"
    stale = out / "files" / "meetings" / "2011-03-01" / "overview.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    build_corpus(
        [_record("minutes_240509", "minutes", "2024-05-09", "minutes.txt")],
        docs,
        out,
    )

    assert not stale.exists()
