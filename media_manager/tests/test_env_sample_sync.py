from __future__ import annotations

import re
from pathlib import Path

RE_GETENV = re.compile(r"""os\.getenv\(\s*["']([A-Z][A-Z0-9_]*)["']""")
RE_ENVIRON = re.compile(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]""")
RE_FLAG_ENABLED = re.compile(r"""_flag_enabled\(\s*["']([A-Z][A-Z0-9_]*)["']\s*\)""")
RE_ENV_TRUTHY = re.compile(r"""_env_truthy\(\s*["']([A-Z][A-Z0-9_]*)["']\s*\)""")
RE_DEFAULT_PATH = re.compile(r"""_default_path\(\s*["']([A-Z][A-Z0-9_]*)["']\s*,""")
RE_DEFAULT_DAYS = re.compile(r"""_default_days\(\s*["']([A-Z][A-Z0-9_]*)["']\s*,""")
RE_ENV_OVERRIDE_PATH = re.compile(r"""_env_override_path\(\s*["']([A-Z][A-Z0-9_]*)["']\s*,""")
RE_ENV_OVERRIDE_DAYS = re.compile(r"""_env_override_days\(\s*["']([A-Z][A-Z0-9_]*)["']\s*,""")
RE_ENV_LINE = re.compile(r"""^([A-Z][A-Z0-9_]*)\s*=""")

SCAN_DIRS = ("media_manager", "migrations", "operator_console", "tools")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _iter_python_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in SCAN_DIRS:
        base = root / directory
        if not base.exists():
            continue
        paths.extend(base.rglob("*.py"))
    return sorted(path for path in paths if path.is_file())


def _declared_env_vars(sample_path: Path) -> set[str]:
    declared: set[str] = set()
    for raw_line in sample_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = RE_ENV_LINE.match(line)
        if match:
            declared.add(match.group(1))
    return declared


def _discovered_env_vars(files: list[Path]) -> set[str]:
    discovered: set[str] = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        discovered.update(RE_GETENV.findall(text))
        discovered.update(RE_ENVIRON.findall(text))
        discovered.update(RE_FLAG_ENABLED.findall(text))
        discovered.update(RE_ENV_TRUTHY.findall(text))
        discovered.update(RE_DEFAULT_PATH.findall(text))
        discovered.update(RE_DEFAULT_DAYS.findall(text))
        discovered.update(RE_ENV_OVERRIDE_PATH.findall(text))
        discovered.update(RE_ENV_OVERRIDE_DAYS.findall(text))
    return discovered


def test_env_sample_covers_runtime_env_reads() -> None:
    root = _repo_root()
    sample_path = root / ".env.sample"
    python_files = _iter_python_files(root)

    declared = _declared_env_vars(sample_path)
    discovered = _discovered_env_vars(python_files)

    missing = sorted(discovered - declared)
    extra = sorted(declared - discovered)

    errors: list[str] = []
    if missing:
        errors.append(f"Missing in .env.sample: {', '.join(missing)}")
    if extra:
        errors.append(f"Declared but not discovered in code scan: {', '.join(extra)}")

    assert not errors, " | ".join(errors)
