from pathlib import Path

from rise.inquiry.discovery import discover_candidates


def test_discovery_merges_multi_query_bm25_and_exact_scans(tmp_path: Path):
    (tmp_path / "one.txt").write_text("Tuition fee adjustment proposal", encoding="utf-8")
    (tmp_path / "two.txt").write_text("Nancy Ip discussed student charges", encoding="utf-8")
    manifest = {
        "one": {"relpath": "one.txt", "role": "agenda_item"},
        "two": {"relpath": "two.txt", "role": "minutes"},
    }

    def fake_retrieve(query, depth):
        return [("one", 4.0)] if "tuition" in query.lower() else [("two", 3.0)]

    result = discover_candidates(
        ["tuition fees", "student charges"], ["Nancy Ip"], fake_retrieve, manifest, tmp_path, depth=50
    )

    assert result.doc_ids == {"one", "two"}
    assert result.scores["one"] == 4.0
    assert "exact_scan:Nancy Ip" in result.sources["two"]
    assert result.queries == ["tuition fees", "student charges"]
