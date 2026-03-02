from __future__ import annotations

import subprocess
from pathlib import Path


def test_artifacts_path_is_gitignored() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "artifacts" / "phase10_safety_probe.txt"

    result = subprocess.run(
        ["git", "check-ignore", "-q", str(target)],
        cwd=repo_root,
        check=False,
    )

    assert result.returncode == 0, "artifacts/ path must be ignored by git"
