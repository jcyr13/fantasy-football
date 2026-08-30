"""Structural guard for the VPS deployment contract (issue #20, docs/adr/0015).

Not a substitute for actually running `docker compose` on the box — it pins the
acceptance criteria that are easy to regress in a one-line edit:

* the long-running services restart themselves (clean recovery after a reboot),
* they have healthchecks (so `web` can wait on `api`, and `docker compose ps`
  reports real status),
* published ports bind through the ``*_BIND`` variables — never a hardcoded
  ``0.0.0.0`` — so an un-configured `up` is loopback-only, not public,
* the sidecar and the Cloudflare fallback are profile-gated, so a plain
  `docker compose up` starts neither.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose() -> dict:
    assert COMPOSE_PATH.is_file(), f"missing {COMPOSE_PATH}"
    data = yaml.safe_load(COMPOSE_PATH.read_text())
    assert isinstance(data, dict) and "services" in data
    return data


@pytest.fixture(scope="module")
def services(compose: dict) -> dict:
    return compose["services"]


def test_expected_services_present(services: dict) -> None:
    assert {"api", "web", "rsidecar", "cloudflared"} <= set(services)


@pytest.mark.parametrize("name", ["api", "web"])
def test_long_running_services_restart_and_have_healthchecks(services: dict, name: str) -> None:
    svc = services[name]
    assert svc.get("restart") == "unless-stopped", (
        f"{name} must be 'restart: unless-stopped' so a reboot brings it back"
    )
    test = svc.get("healthcheck", {}).get("test")
    assert test, f"{name} needs a healthcheck"


@pytest.mark.parametrize("name", ["api", "web"])
def test_published_ports_bind_through_a_variable(services: dict, name: str) -> None:
    ports = services[name].get("ports", [])
    assert ports, f"{name} publishes a port"
    for entry in ports:
        spec = entry if isinstance(entry, str) else entry.get("host_ip", "")
        assert "BIND" in spec, (
            f"{name} port {entry!r} must bind via ${{WEB_BIND}}/${{API_BIND}}, "
            "not a hardcoded address"
        )
        assert "0.0.0.0" not in spec, f"{name} port {entry!r} hardcodes 0.0.0.0"


def test_api_default_bind_is_loopback(services: dict) -> None:
    # The default in the ${API_BIND:-...} expansion must be loopback so an
    # un-configured `docker compose up` is never exposed.
    for entry in services["api"]["ports"]:
        spec = entry if isinstance(entry, str) else str(entry)
        assert ":-127.0.0.1}" in spec, f"api port {entry!r} should default API_BIND to 127.0.0.1"


def test_web_waits_on_api_health(services: dict) -> None:
    depends = services["web"].get("depends_on", {})
    assert "api" in depends
    # dict form carries the condition; list form is just ordering.
    if isinstance(depends, dict):
        assert depends["api"].get("condition") == "service_healthy"


def test_rsidecar_is_a_profile_gated_one_shot(services: dict) -> None:
    svc = services["rsidecar"]
    assert svc.get("restart") == "no", "rsidecar is a one-shot, not a service"
    assert "sidecar" in svc.get("profiles", []), "rsidecar must be behind the 'sidecar' profile"


def test_cloudflared_is_profile_gated(services: dict) -> None:
    # The fallback path must never start on a plain `docker compose up`.
    assert "cloudflare" in services["cloudflared"].get("profiles", [])


def test_no_service_starts_unprofiled_except_api_and_web(services: dict) -> None:
    unprofiled = {n for n, s in services.items() if not s.get("profiles")}
    assert unprofiled == {"api", "web"}
