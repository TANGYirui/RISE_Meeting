import subprocess
import sys
from pathlib import Path


def test_source_dir_is_required():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "build_uac_corpus.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--source-dir" in result.stderr
    assert "required" in result.stderr
