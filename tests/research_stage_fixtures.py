"""Structured model substitutes that still execute the feasibility probe locally."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import research_stage_execution
from tests.baseline_fixtures import real_baseline_runtime  # noqa: F401


def stage_payload(root: Path, phase: str, catalog: dict, *, assessment="supported") -> dict:
    (root / "outputs").mkdir(exist_ok=True)
    result = {"status": "completed", "summary": "Evidence-backed research task completed for human review."}
    payload = {"status": "completed", "raw_events": []}
    baseline_id = next((key for key, item in catalog.items() if item["kind"] == "baseline_result"), None)
    if phase in {"proposal", "feasibility"}:
        assert baseline_id is not None
        citation = {"reference_id": baseline_id, "quote": '"observed_value": 2.0'}
    if phase == "proposal":
        result.update(routes=[{
            "id": f"route-{suffix}", "title": title,
            "hypothesis": "A controlled methodological change may improve reproducibility.",
            "approach": "Compare a proposed method against the accepted baseline.",
            "success_criteria": ["Compare observed error using the same input and declared tolerance"],
            "risks": ["The available dataset may not generalize"], "citations": [citation],
        } for suffix, title in (("a", "Controlled method comparison"), ("b", "Sensitivity analysis"), ("c", "Independent validation"))],
                      recommended_route_id="route-a")
    elif phase == "feasibility":
        script = (
            "import json\nfrom pathlib import Path\n"
            "catalog = json.loads(Path('inputs/evidence.json').read_text())\n"
            "baseline = next(item for item in catalog.values() if item['kind'] == 'baseline_result')\n"
            "value = json.loads(baseline['text'])['metrics'][0]['observed_value']\n"
            "Path('outputs/probe.json').write_text(json.dumps({'probe_value': value}))\n"
        )
        (root / "outputs/probe.py").write_text(script)
        subprocess.run([sys.executable, "outputs/probe.py"], cwd=root, check=True)
        (root / "outputs/feasibility.md").write_text("# Feasibility\nA local smoke check, not experimental validation.")
        checks = [{"dimension": dimension, "assessment": assessment, "finding": finding, "citations": citations}
                  for dimension, finding, citations in (
                      ("scientific_rationale", "An executed baseline is available for a controlled comparison.", [citation]),
                      ("method_validation", "The local probe returned 2.0.", [{"reference_id": "execution:observations", "quote": '"probe_value": 2.0'}]),
                      ("controls_resources", "The proposed controls retain an executed baseline reference.", [citation]),
                  )]
        result.update(checks=checks, protocol={
            "hypothesis": "The proposed method may improve robustness.", "steps": ["Repeat the baseline with controlled input"],
            "endpoints": ["Absolute numeric error"], "controls": ["Accepted baseline", "Negative control"],
            "resources": ["Installed Python runtime"], "risks": ["Limited dataset coverage"],
            "stopping_rules": ["Stop if inputs or controls are unavailable"],
        }, environment={"python": sys.version.split()[0]}, script_path="outputs/probe.py",
                      observations_path="outputs/probe.json", report_path="outputs/feasibility.md")
        payload["raw_events"] = [{"type": "item.completed", "item": {
            "type": "command_execution", "id": "probe-command", "status": "completed", "exit_code": 0,
            "command": "python outputs/probe.py",
        }}]
    else:
        source_id = next(iter(catalog))
        source = catalog[source_id]
        citation = {"reference_id": source_id, "quote": source["text"][:1000]}
        result.update(title="Evidence-bound research study", sections=[
            {"heading": "Introduction", "blocks": [{"kind": "claim", "basis": source["kind"],
                "text": "The available record documents a reference methodology.", "citations": [citation]}]},
            {"heading": "Methods", "blocks": [{"kind": "proposal", "text": "A controlled comparison is proposed."}]},
            {"heading": "Results", "blocks": [{"kind": "claim", "basis": source["kind"],
                "text": "The supplied evidence is retained for review.", "citations": [citation]}]},
            {"heading": "Discussion", "blocks": [{"kind": "interpretation", "basis": source["kind"],
                "text": "The evidence motivates further independent assessment.", "citations": [citation]}]},
            {"heading": "Limitations", "blocks": [{"kind": "limitation", "text": "Scientific validity requires human review."}]},
        ])
    (root / "outputs/result.json").write_text(json.dumps(result))
    return payload


@pytest.fixture
def research_stage_runtime(monkeypatch, real_baseline_runtime):
    async def runtime(*, cwd, **kwargs):
        root = Path(cwd)
        manifest = json.loads((root / "inputs/manifest.json").read_text())
        catalog = json.loads((root / "inputs/evidence.json").read_text())
        assert kwargs["sandbox"] == "workspace-write"
        return stage_payload(root, manifest["phase"], catalog)

    monkeypatch.setattr(research_stage_execution, "run_codex_runtime", runtime)
    return runtime
