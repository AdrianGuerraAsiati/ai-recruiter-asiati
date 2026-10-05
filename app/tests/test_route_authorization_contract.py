"""Authorization regression guard for HTTP routes.

The goal is not to replace endpoint-specific RBAC tests. It prevents a new
business endpoint from being added without an authentication dependency.
Public callbacks and device-authenticated kiosk endpoints are explicitly
allow-listed because they use different security mechanisms.
"""

from fastapi.routing import APIRoute

from app.main import app


PUBLIC_PATHS = {
    "/live",
    "/api/live",
    "/ready",
    "/api/ready",
    "/health",
    "/api/health",
    "/api/auth/login",
    "/api/auth/login/new-password",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/integrations/gmail/oauth/callback",
}

DEVICE_AUTH_PATHS = {
    "/v1/kiosk/context",
    "/v1/kiosk/recognize",
}


def _dependency_calls(dependant):
    calls = []
    for item in dependant.dependencies:
        if item.call is not None:
            calls.append(item.call)
        calls.extend(_dependency_calls(item))
    return calls


def _has_authentication_dependency(route: APIRoute) -> bool:
    for call in _dependency_calls(route.dependant):
        module = str(getattr(call, "__module__", ""))
        name = str(getattr(call, "__name__", ""))

        # require_permission()/require_role() return a dependency closure in app.deps.
        if module == "app.deps" and name in {
            "dependency",
            "get_current_principal",
            "get_current_user",
        }:
            return True

        if name == "get_indeed_resume_agent_principal":
            return True

    return False


def test_business_routes_require_authentication_dependency():
    unsecured = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith(("/api/", "/v1/")):
            continue
        if route.path in PUBLIC_PATHS or route.path in DEVICE_AUTH_PATHS:
            continue
        if not _has_authentication_dependency(route):
            unsecured.append(f"{','.join(sorted(route.methods or []))} {route.path}")

    assert unsecured == [], "Routes without an authentication dependency: " + "; ".join(unsecured)
