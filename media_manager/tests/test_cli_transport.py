from __future__ import annotations

from media_manager.app import cli


def test_cli_status_http_transport_json(monkeypatch, capsys) -> None:
    def _fake_http_call_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return 200, {
            "ok": True,
            "workflow_version": "v2-service-layer",
            "schema_version": "phase13",
            "generated_at": "2026-03-03T00:00:00+00:00",
            "data": {"active_phase": "phase13"},
            "errors": [],
        }

    monkeypatch.setattr(cli, "_http_call_json", _fake_http_call_json)
    exit_code = cli.main(["--transport", "http", "--api", "http://localhost:8000", "status", "--json"])
    assert exit_code == 0
    assert '"active_phase": "phase13"' in capsys.readouterr().out


def test_cli_operator_http_transport_runs_resource(monkeypatch, capsys) -> None:
    def _fake_http_call_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return 200, {
            "ok": True,
            "workflow_version": "v2-service-layer",
            "schema_version": "phase13",
            "generated_at": "2026-03-03T00:00:00+00:00",
            "data": {"result": [{"run_id": "abc"}]},
            "errors": [],
        }

    monkeypatch.setattr(cli, "_http_call_json", _fake_http_call_json)
    exit_code = cli.main(["--transport", "http", "--api", "http://localhost:8000", "operator", "runs", "--json"])
    assert exit_code == 0
    assert '"run_id": "abc"' in capsys.readouterr().out
