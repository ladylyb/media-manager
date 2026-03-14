from __future__ import annotations

from pathlib import Path
import tomllib


def test_project_scripts_expose_api_entrypoint_only() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    scripts = payload["project"]["scripts"]
    testpaths = payload["tool"]["pytest"]["ini_options"]["testpaths"]
    cli_module = Path(__file__).resolve().parents[2] / "media_manager" / "app" / "cli.py"

    assert scripts == {"media-manager-api": "operator_console.main:main"}
    assert testpaths == ["media_manager/tests", "operator_console/tests"]
    assert not cli_module.exists()
