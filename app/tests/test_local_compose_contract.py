"""Static regression checks for the isolated development Compose stack."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
API_DOCKERFILE = ROOT / "Dockerfile"
NGINX = ROOT / "frontend-react" / "nginx.conf"


def test_compose_services_and_proxy_resolve():
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = data["services"]
    assert {"db", "migrate", "ai-recruiter-api", "web"} <= set(services)
    nginx = NGINX.read_text(encoding="utf-8")
    assert "proxy_pass http://ai-recruiter-api:80;" in nginx
    assert "ai-recruiter-api" in services["web"]["depends_on"]
    assert services["web"]["depends_on"]["ai-recruiter-api"]["condition"] == "service_healthy"


def test_compose_api_uses_container_port_and_real_readiness():
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    api = data["services"]["ai-recruiter-api"]
    assert "EXPOSE 80" in dockerfile
    assert '"--port", "80"' in dockerfile
    check = " ".join(api["healthcheck"]["test"])
    assert "127.0.0.1:80/api/ready" in check
    assert "127.0.0.1:8000" not in check
    assert "ports" not in api


def test_compose_migrates_before_start_and_keeps_local_services_private():
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = data["services"]
    migrate = services["migrate"]
    assert migrate["depends_on"]["db"]["condition"] == "service_healthy"
    assert migrate["command"][-2:] == ["upgrade", "head"]
    assert services["ai-recruiter-api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert "ports" not in services["db"]
    assert services["web"]["ports"] == ["127.0.0.1:${WEB_PORT:-8080}:80"]
    assert all(k not in services for k in ("worker", "odoo"))


def test_local_compose_disables_external_ingestion_and_employment_integrations():
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    env = data["services"]["ai-recruiter-api"]["environment"]
    assert env["GMAIL_ENABLED"] == "false"
    assert env["INDEED_ENABLED"] == "false"
    assert env["ODOO_ENABLED"] == "false"
    assert env["ALLOW_PUBLIC_REGISTRATION"] == "false"
    assert env["DATABASE_URL"].endswith("@db:5432/ai_recruiter")
