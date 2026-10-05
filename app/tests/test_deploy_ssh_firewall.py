"""Contracts for zero-cost ephemeral SSH access during production deploys."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
FIREWALL_SCRIPT = ROOT / "scripts" / "manage-lightsail-ssh-firewall.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_deploy_restricts_ssh_before_requesting_instance_credentials():
    workflow = _read(WORKFLOW)

    restrict = workflow.index("- name: Restrict SSH to current runner")
    credentials = workflow.index("- name: Acquire certified Lightsail SSH credentials")
    first_ssh = workflow.index('ssh "${SSH[@]}"')

    assert restrict < credentials < first_ssh
    assert "https://checkip.amazonaws.com" in workflow
    assert "manage-lightsail-ssh-firewall.sh open" in workflow


def test_deploy_always_closes_temporary_ssh_access():
    workflow = _read(WORKFLOW)

    close = workflow.index("- name: Close temporary SSH firewall access")
    cleanup = workflow.index("- name: Cleanup temporary SSH credentials")

    assert close < cleanup
    close_block = workflow[close:cleanup]
    assert "if: always()" in close_block
    assert "manage-lightsail-ssh-firewall.sh close" in close_block


def test_firewall_helper_uses_atomic_port_replacement_and_runner_32():
    script = _read(FIREWALL_SCRIPT)

    assert "lightsail get-instance" in script
    assert "lightsail put-instance-public-ports" in script
    assert 'RUNNER_CIDR="$RUNNER_IP/32"' in script
    assert "open-instance-public-ports" not in script
    assert "0.0.0.0/0" not in script


def test_firewall_helper_closes_ssh_and_preserves_non_ssh_ports():
    script = _read(FIREWALL_SCRIPT)

    assert 'MODE="${1:?usage: manage-lightsail-ssh-firewall.sh open <ipv4>|close}"' in script
    assert "fromPort == 22 and .toPort == 22" in script
    assert "Refuse to alter a broad TCP range" in script
    assert "LIGHTSAIL_SSH_CLOSED" in script
    assert "LIGHTSAIL_SSH_RESTRICTED" in script
