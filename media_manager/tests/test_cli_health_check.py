from __future__ import annotations

import json
from urllib import error as urllib_error

from media_manager.app.cli import main


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        _ = exc_type, exc, tb


def test_cli_health_check_returns_zero_when_clean(monkeypatch, capsys) -> None:
    def _fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        _ = request, timeout
        return _FakeResponse(
            {
                "total_files": 10,
                "missing_hash": 0,
                "hash_mismatches": 0,
                "deleted_rows_skipped": 1,
                "sample_missing_hash_paths": [],
                "sample_mismatch_paths": [],
            }
        )

    monkeypatch.setattr("media_manager.app.cli.urllib_request.urlopen", _fake_urlopen)

    exit_code = main(["health-check", "--audit-hashes"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Ledger Hash Audit" in stdout
    assert "Missing hash: 0" in stdout


def test_cli_health_check_returns_one_when_issues_found(monkeypatch) -> None:
    def _fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        _ = request, timeout
        return _FakeResponse(
            {
                "total_files": 10,
                "missing_hash": 2,
                "hash_mismatches": 1,
                "deleted_rows_skipped": 1,
                "sample_missing_hash_paths": ["/x"],
                "sample_mismatch_paths": ["/y"],
            }
        )

    monkeypatch.setattr("media_manager.app.cli.urllib_request.urlopen", _fake_urlopen)

    exit_code = main(["health-check", "--audit-hashes"])

    assert exit_code == 1


def test_cli_health_check_transport_error_returns_two(monkeypatch, capsys) -> None:
    def _fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        _ = request, timeout
        raise urllib_error.URLError("unreachable")

    monkeypatch.setattr("media_manager.app.cli.urllib_request.urlopen", _fake_urlopen)

    exit_code = main(["health-check", "--audit-hashes"])

    assert exit_code == 2
    assert "request failed" in capsys.readouterr().err.lower()


def test_cli_health_check_root_is_forwarded_in_request(monkeypatch) -> None:
    captured = {"url": ""}

    def _fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        _ = timeout
        captured["url"] = request.full_url
        return _FakeResponse(
            {
                "total_files": 1,
                "missing_hash": 0,
                "hash_mismatches": 0,
                "deleted_rows_skipped": 0,
                "sample_missing_hash_paths": [],
                "sample_mismatch_paths": [],
            }
        )

    monkeypatch.setattr("media_manager.app.cli.urllib_request.urlopen", _fake_urlopen)

    exit_code = main(
        [
            "health-check",
            "--audit-hashes",
            "--api",
            "http://localhost:8000",
            "--root",
            "/dataset",
            "--sample-limit",
            "25",
        ]
    )

    assert exit_code == 0
    assert "root_path=%2Fdataset" in captured["url"]
    assert "sample_limit=25" in captured["url"]


def test_cli_health_check_requires_audit_flag(capsys) -> None:
    exit_code = main(["health-check"])
    assert exit_code == 2
    assert "--audit-hashes" in capsys.readouterr().err
