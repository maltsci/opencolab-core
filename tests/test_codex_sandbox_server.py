import importlib.util
from pathlib import Path


def _load_codex_sandbox_server():
    server_path = Path(__file__).resolve().parents[1] / "codex-sandbox" / "server.py"
    spec = importlib.util.spec_from_file_location("codex_sandbox_server", server_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_exec_command_uses_current_cli_flags():
    server = _load_codex_sandbox_server()

    command = server._build_codex_exec_command(
        workdir="/workspace",
        sandbox="workspace-write",
        model="malt-simple",
        api_base="https://llm.example.test/v1",
        output_file="/tmp/codex-output.txt",
    )

    assert "--ask-for-approval" not in command
    assert command[0:2] == ["codex", "exec"]
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "--model" in command
    assert command[command.index("--model") + 1] == "malt-simple"
    assert "model_provider=\"opencolab\"" in command
    assert "model_providers.opencolab.base_url=\"https://llm.example.test/v1\"" in command
    assert "model_providers.opencolab.env_key=\"OPENAI_API_KEY\"" in command
    assert "model_providers.opencolab.wire_api=\"responses\"" in command


def test_codex_sandbox_requires_api_key(monkeypatch):
    server = _load_codex_sandbox_server()

    monkeypatch.setattr(server, "SANDBOX_API_KEY", "")

    try:
        server._require_auth(None)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
    else:
        raise AssertionError("sandbox accepted unauthenticated request")


def test_codex_sandbox_rejects_workdir_outside_workspace():
    server = _load_codex_sandbox_server()

    try:
        server._safe_workdir("/tmp")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("sandbox accepted workdir outside the workspace")
