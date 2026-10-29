import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="OpenColab Codex Sandbox")
logger = logging.getLogger("codex-sandbox")

SANDBOX_API_KEY = os.environ.get("SANDBOX_API_KEY", "").strip()
DEFAULT_WORKDIR = os.environ.get("CODEX_WORKDIR", "/workspace").strip() or "/workspace"
DEFAULT_SANDBOX = os.environ.get("CODEX_DEFAULT_SANDBOX", "workspace-write").strip() or "workspace-write"
DEFAULT_TIMEOUT = int(os.environ.get("CODEX_RUN_TIMEOUT_SECONDS", "1800"))
# Wire protocol used when talking to an OpenAI-compatible api_base. Some
# gateways (e.g. LiteLLM proxies) cannot sustain Responses-API streaming;
# set CODEX_WIRE_API=chat there to fall back to Chat Completions.
WIRE_API = os.environ.get("CODEX_WIRE_API", "responses").strip() or "responses"


class CodexRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    cwd: str | None = None
    sandbox: str | None = None
    provider: str | None = None
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    source: str | None = None


def _require_auth(authorization: str | None) -> None:
    if not SANDBOX_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox API key is not configured",
        )
    expected = f"Bearer {SANDBOX_API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _safe_workdir(raw_cwd: str | None) -> str:
    workspace_root = Path(DEFAULT_WORKDIR).resolve()
    cwd = (raw_cwd or DEFAULT_WORKDIR).strip() or DEFAULT_WORKDIR
    resolved = Path(cwd).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cwd must be inside the configured workspace",
        ) from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def _build_env(body: CodexRunRequest) -> dict[str, str]:
    env = os.environ.copy()
    if body.api_key:
        env["OPENAI_API_KEY"] = body.api_key
    if body.api_base:
        env["OPENAI_BASE_URL"] = body.api_base
    env["CODEX_HOME"] = env.get("CODEX_HOME", "/app/.codex")
    return env


def _parse_json_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            events.append({"type": "stdout", "text": line})
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _extract_content(events: list[dict[str, Any]], fallback: str) -> str:
    for event in reversed(events):
        for key in ("message", "content", "text", "last_message"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        item = event.get("item")
        if isinstance(item, dict):
            text = item.get("text") or item.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return fallback.strip()


def _extract_usage(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        usage = event.get("usage")
        if isinstance(usage, dict) and usage:
            return usage
    return None


def _build_codex_exec_command(
    *,
    workdir: str,
    sandbox: str,
    model: str,
    api_base: str | None,
    output_file: str,
) -> list[str]:
    provider_config: list[str] = []
    if api_base:
        provider_config = [
            "-c",
            'model_provider="opencolab"',
            "-c",
            'model_providers.opencolab.name="OpenColab"',
            "-c",
            f'model_providers.opencolab.base_url="{api_base}"',
            "-c",
            'model_providers.opencolab.env_key="OPENAI_API_KEY"',
            "-c",
            f'model_providers.opencolab.wire_api="{WIRE_API}"',
        ]

    return [
        "codex",
        "exec",
        *provider_config,
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        sandbox,
        "--cd",
        workdir,
        "--model",
        model,
        "--output-last-message",
        output_file,
        "-",
    ]


@app.get("/health")
async def health(authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    codex_path = shutil.which("codex")
    return {
        "status": "ok" if codex_path else "missing_codex",
        "codex_command": codex_path,
        "workdir": DEFAULT_WORKDIR,
        "sandbox": DEFAULT_SANDBOX,
    }


@app.post("/run")
async def run_codex(
    body: CodexRunRequest,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    if not shutil.which("codex"):
        raise HTTPException(status_code=503, detail="codex command not found")
    if not body.api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    if not body.model:
        raise HTTPException(status_code=400, detail="model is required")

    workdir = _safe_workdir(body.cwd)
    sandbox = (body.sandbox or DEFAULT_SANDBOX).strip() or DEFAULT_SANDBOX
    output_file = tempfile.NamedTemporaryFile(delete=False)
    output_file.close()
    cmd = _build_codex_exec_command(
        workdir=workdir,
        sandbox=sandbox,
        model=body.model,
        api_base=body.api_base,
        output_file=output_file.name,
    )
    env = _build_env(body)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    try:
        proc.stdin.write(body.prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
    except (BrokenPipeError, ConnectionResetError):
        pass  # process exited before reading the prompt; stderr will explain

    # Tee codex's JSON event stream into the run dir so the backend can
    # report live progress while the run is still executing.
    progress_path = Path(workdir) / "progress.jsonl"
    stdout_lines: list[str] = []

    async def _pump_stdout() -> None:
        with progress_path.open("w", encoding="utf-8") as handle:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                stdout_lines.append(text)
                handle.write(text)
                handle.flush()

    stderr_chunks: list[bytes] = []

    async def _read_stderr() -> None:
        stderr_chunks.append(await proc.stderr.read())

    try:
        await asyncio.wait_for(
            asyncio.gather(_pump_stdout(), _read_stderr(), proc.wait()),
            timeout=DEFAULT_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        logger.error(
            "codex run timed out after %ss: workdir=%s model=%s",
            DEFAULT_TIMEOUT,
            workdir,
            body.model,
        )
        raise HTTPException(status_code=504, detail="codex run timed out") from exc
    finally:
        try:
            content = Path(output_file.name).read_text(encoding="utf-8").strip()
        except OSError:
            content = ""
        with contextlib.suppress(OSError):
            os.unlink(output_file.name)

    stdout = "".join(stdout_lines)
    stderr = stderr_chunks[0].decode("utf-8", errors="replace") if stderr_chunks else ""
    events = _parse_json_events(stdout)
    if proc.returncode != 0:
        logger.error(
            "codex run failed: returncode=%s workdir=%s model=%s api_base=%s stderr=%s stdout_tail=%s",
            proc.returncode,
            workdir,
            body.model,
            body.api_base,
            stderr.strip()[:2000],
            stdout.strip()[-1000:],
        )
        raise HTTPException(
            status_code=502,
            detail=stderr.strip() or stdout.strip() or "codex run failed",
        )

    return {
        "status": "completed",
        "content": content or _extract_content(events, stdout),
        "raw_events": events,
        "stderr": stderr.strip(),
        "usage": _extract_usage(events),
        "source": body.source,
    }
