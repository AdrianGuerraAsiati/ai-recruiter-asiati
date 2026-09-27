"""Parse GitHub workflows as YAML to catch structural edit regressions."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "deploy.yml",
    ROOT / ".github" / "workflows" / "security.yml",
)


def test_workflows_are_valid_yaml_documents():
    for workflow in WORKFLOWS:
        payload = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        assert isinstance(payload, dict), workflow
        assert "jobs" in payload, workflow
