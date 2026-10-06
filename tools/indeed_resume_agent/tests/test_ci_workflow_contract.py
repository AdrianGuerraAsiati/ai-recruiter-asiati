from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "indeed-resume-agent.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_primary_ci_runs_agent_tests_automatically():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "tools/indeed_resume_agent/requirements.txt" in text
    assert "python -m pytest -q tools/indeed_resume_agent/tests" in text


def test_primary_ci_installs_chromium_for_golden_browser_fixtures():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "playwright install --with-deps chromium" in text
    assert "test_browser_live_fixtures.py" not in text  # discovered by the test directory run


def test_agent_build_workflow_runs_only_after_main_changes_or_manual_dispatch():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert 'tools/indeed_resume_agent/**' in text


def test_agent_workflow_builds_windows_onedir_and_uploads_artifact():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in text
    assert "tools\\indeed_resume_agent\\build.ps1" in text
    artifact_action = re.search(r"actions/upload-artifact@v([0-9]+)", text)
    assert artifact_action is not None
    assert int(artifact_action.group(1)) >= 4
    assert "ASIATI-Resume-Agent-Windows-SIGNED" in text
    assert "--self-test" in text
    assert "Execute packaged binary self-test" in text


def test_primary_ci_skips_agent_jobs_when_agent_paths_are_unchanged():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "Detect Resume Agent changes" in text
    assert "resume_agent: ${{ steps.filter.outputs.resume_agent }}" in text
    assert "if: needs.changes.outputs.resume_agent == 'true'" in text
    assert "Resume Agent tests (Linux)" in text
    assert "Resume Agent (Windows + Chrome)" in text


def test_primary_ci_revalidates_agent_when_root_python_dependencies_change():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "requirements[.]txt$" in text


def test_agent_workflow_requires_authenticode_before_publishing_distribution_artifact():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "Sign Windows executable" in text
    assert "Verify Authenticode signature" in text
    assert "tools\\indeed_resume_agent\\sign.ps1" in text
    assert "WINDOWS_CODE_SIGNING_PFX_BASE64" in text
    assert "WINDOWS_CODE_SIGNING_PFX_PASSWORD" in text
    assert "steps.signing.outputs.signed == 'true'" in text
    assert "No distributable artifact will be published" in text
