from __future__ import annotations

from media_manager.app import cli


def test_cli_db_reset_dry_run_success(monkeypatch, capsys) -> None:
    def _fake_http_call_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return 200, {
            "ok": True,
            "data": {
                "result": {
                    "success": True,
                    "dry_run": True,
                    "affected_tables": ["media_file"],
                    "message": "Dry-run only. No data deleted.",
                }
            },
            "errors": [],
        }

    monkeypatch.setattr(cli, "_http_call_json", _fake_http_call_json)
    exit_code = cli.main(["db-reset", "--dry-run"])
    assert exit_code == 0
    assert "Dry run: True" in capsys.readouterr().out


def test_cli_db_reset_requires_challenge_without_dry_run(capsys) -> None:
    exit_code = cli.main(["db-reset"])
    assert exit_code == 2
    assert "--challenge-word is required" in capsys.readouterr().err


def test_cli_db_reset_wrong_challenge_semantic_failure(monkeypatch) -> None:
    def _fake_http_call_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return 400, {
            "ok": False,
            "data": {},
            "errors": [{"code": "VALIDATION_ERROR", "message": "challenge_word is incorrect."}],
        }

    monkeypatch.setattr(cli, "_http_call_json", _fake_http_call_json)
    exit_code = cli.main(["db-reset", "--challenge-word", "wrong"])
    assert exit_code == 1


def test_cli_db_reset_json_output(monkeypatch, capsys) -> None:
    def _fake_http_call_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return 200, {
            "ok": True,
            "data": {"result": {"success": True, "dry_run": True, "affected_tables": [], "message": "Dry-run only. No data deleted."}},
            "errors": [],
        }

    monkeypatch.setattr(cli, "_http_call_json", _fake_http_call_json)
    exit_code = cli.main(["db-reset", "--dry-run", "--json"])
    assert exit_code == 0
    assert '"success": true' in capsys.readouterr().out.lower()


def test_cli_db_reset_http_failure_returns_2(monkeypatch, capsys) -> None:
    def _fake_http_call_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        raise RuntimeError("connection failed")

    monkeypatch.setattr(cli, "_http_call_json", _fake_http_call_json)
    exit_code = cli.main(["db-reset", "--dry-run"])
    assert exit_code == 2
    assert "DB reset API request failed" in capsys.readouterr().err
