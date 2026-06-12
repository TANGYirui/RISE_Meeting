from pathlib import Path

from rise.run_storage import default_result_root, query_workspace


def test_default_result_root_uses_result_directory(tmp_path: Path) -> None:
    assert default_result_root(tmp_path, "rise_example") == (
        tmp_path / "result" / "rise_example"
    )


def test_temporary_query_workspace_is_removed_after_use(tmp_path: Path) -> None:
    with query_workspace(tmp_path / "result" / "run", "question-1") as workspace:
        workspace_path = workspace
        assert workspace.exists()
        (workspace / "evidence.txt").write_text("evidence", encoding="utf-8")

    assert not workspace_path.exists()
    assert not (tmp_path / "result" / "run" / "_working").exists()


def test_kept_query_workspace_remains_under_result_directory(tmp_path: Path) -> None:
    result_root = tmp_path / "result" / "run"

    with query_workspace(result_root, "question-1", keep=True) as workspace:
        (workspace / "evidence.txt").write_text("evidence", encoding="utf-8")

    assert workspace == result_root / "_working" / "qidquestion-1"
    assert (workspace / "evidence.txt").read_text(encoding="utf-8") == "evidence"
