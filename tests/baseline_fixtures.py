"""Local script execution behind a substituted Codex provider for integration tests."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import baseline_execution


def completed_output(root: Path, source_id: str, observed=2.0):
    comparison = {
        "source_id": source_id, "source_quote": "The baseline mean is 2.0.",
        "metric": "mean", "reported_value": 2.0, "observed_value": observed,
        "unit": "arbitrary units", "absolute_tolerance": 0.01,
        "tolerance_reason": "Reported precision is two decimal places.",
    }
    (root / "outputs").mkdir(exist_ok=True)
    # The test runner executes an actual script; the fixture only substitutes the provider.
    script = (
        "import json\nfrom pathlib import Path\n"
        f"comparisons = {comparison!r}\n"
        f"comparisons['observed_value'] = sum([1.0, {2 * observed - 1!r}]) / 2\n"
        "Path('outputs/observations.json').write_text(json.dumps([comparisons]))\n"
    )
    (root / "outputs/reproduce.py").write_text(script)
    subprocess.run([sys.executable, "outputs/reproduce.py"], cwd=root, check=True)
    (root / "outputs/report.md").write_text("# Baseline\nA local calculation; scientific review required.")
    result = {"status": "completed", "summary": "Executed the supplied baseline calculation.",
              "environment": {"python": sys.version.split()[0]}, "metrics": [comparison],
              "script_path": "outputs/reproduce.py", "observations_path": "outputs/observations.json",
              "report_path": "outputs/report.md"}
    (root / "outputs/result.json").write_text(json.dumps(result))
    return {"status": "completed", "raw_events": [{"type": "item.completed", "item": {
        "type": "command_execution", "id": "command-1", "status": "completed", "exit_code": 0,
        "command": "python outputs/reproduce.py",
    }}]}


@pytest.fixture
def real_baseline_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "codex_runtime_enabled", True)
    monkeypatch.setattr(settings, "codex_runtime_workspace_dir", str(tmp_path / "workspace"))
    monkeypatch.setattr(settings, "codex_runtime_sandbox_workspace_dir", None)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    async def runtime(*, cwd, **kwargs):
        root = Path(cwd)
        manifest = json.loads((root / "inputs/manifest.json").read_text())
        source = next(item for item in manifest["sources"] if item["status"] == "available")
        assert kwargs["sandbox"] == "workspace-write"
        return completed_output(root, source["source_id"])

    monkeypatch.setattr(baseline_execution, "run_codex_runtime", runtime)
    from app.services import research_stage_execution

    async def unavailable_stage(**kwargs):
        raise RuntimeError("Research stage provider is not configured by this test")

    monkeypatch.setattr(research_stage_execution, "run_codex_runtime", unavailable_stage)
    return runtime
