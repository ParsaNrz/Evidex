from __future__ import annotations

import hashlib
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from filelock import FileLock

from evidex.api import COOKIE, create_app
from evidex.auth import AuthStore
from evidex.models import Stage
from evidex.runtime import Settings, make_provider

HEADERS = {"X-Evidex-Request": "1"}
PASSWORD = "a-long-test-password-only"


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, demo=True, secure_cookies=False)


def register(client, email="student@example.test"):
    response = client.post(
        "/api/auth/register", headers=HEADERS, json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response


def create(client, brief):
    response = client.post("/api/projects", headers=HEADERS, json=brief.model_dump(mode="json"))
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def action(client, job_id, **body):
    return client.post(f"/api/projects/{job_id}/actions", headers=HEADERS, json=body)


def test_auth_sessions_csrf_validation_and_logout(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/projects").status_code == 401
        assert client.post("/api/auth/register", json={}).status_code == 403
        assert (
            client.post(
                "/api/auth/register", headers={**HEADERS, "Sec-Fetch-Site": "cross-site"}, json={}
            ).status_code
            == 403
        )
        bad = client.post(
            "/api/auth/register", headers=HEADERS, json={"email": "bad", "password": "secret"}
        )
        assert bad.status_code == 422 and "secret" not in bad.text
        response = register(client)
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        token = client.cookies[COOKIE]
        assert client.get("/api/auth/me").status_code == 200
        # Neither passwords nor raw session tokens are persisted.
        with app.state.auth.connection() as db:
            row = db.execute("SELECT * FROM users").fetchone()
            session = db.execute("SELECT * FROM sessions").fetchone()
            assert PASSWORD not in row["password_hash"]
            assert session["token_hash"] != token
        assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204
        client.cookies.set(COOKIE, token, domain="testserver.local", path="/")
        assert client.get("/api/auth/me").status_code == 401
        response = client.post(
            "/api/auth/login",
            headers=HEADERS,
            json={"email": "STUDENT@example.test", "password": PASSWORD},
        )
        assert response.status_code == 200
        assert client.cookies[COOKIE] != token
        with app.state.auth.connection() as db:
            db.execute("UPDATE sessions SET expires=0")
        assert client.get("/api/auth/me").status_code == 401


def test_secure_cookie_registration_switch_and_login_throttling(settings):
    app = create_app(replace(settings, secure_cookies=True))
    with TestClient(app, base_url="https://testserver") as client:
        assert "Secure" in register(client).headers["set-cookie"]
        for _ in range(10):
            r = client.post(
                "/api/auth/login",
                headers=HEADERS,
                json={"email": "missing@example.test", "password": PASSWORD},
            )
            assert r.status_code == 401
        assert (
            client.post(
                "/api/auth/login",
                headers=HEADERS,
                json={"email": "missing@example.test", "password": PASSWORD},
            ).status_code
            == 429
        )
    with TestClient(create_app(replace(settings, registration=False))) as client:
        assert (
            client.post(
                "/api/auth/register",
                headers=HEADERS,
                json={"email": "new@example.test", "password": PASSWORD},
            ).status_code
            == 403
        )


def test_project_isolation_for_every_route_and_restart(settings, brief):
    app = create_app(settings)
    with TestClient(app) as first, TestClient(app) as second:
        register(first)
        job_id = create(first, brief)
        register(second, "other@example.test")
        assert second.get("/api/projects").json() == []
        assert second.get(f"/api/projects/{job_id}").status_code == 404
        for verb in ["run", "approve", "reject", "retry", "cancel"]:
            assert (
                action(second, job_id, action=verb, stage="plan", feedback="test").status_code
                == 404
            )
        for fmt in ["docx", "pdf", "json"]:
            assert second.get(f"/api/projects/{job_id}/downloads/{fmt}").status_code == 404
        assert action(first, job_id, action="approve", stage="plan").status_code == 409
        assert action(first, job_id, action="retry", feedback="").status_code == 422
        assert first.get(f"/api/projects/{job_id}/downloads/pdf").status_code == 409
        token = first.cookies[COOKIE]
    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.set(COOKIE, token)
        assert restarted.get("/api/projects").json()[0]["job"]["job_id"] == job_id


def test_live_unconfigured_fails_without_fixtures(settings, brief):
    with TestClient(create_app(replace(settings, demo=False))) as client:
        register(client)
        response = client.post("/api/projects", headers=HEADERS, json=brief.model_dump(mode="json"))
        assert response.status_code == 503
        assert client.get("/api/projects").json() == []


def test_concurrent_runs_rejected_and_browser_workflow_exports(settings, brief):
    completed = threading.Event()
    entered = threading.Event()
    release = threading.Event()

    def factory(settings, *, demo):
        provider = make_provider(settings, demo=demo)
        original = provider.complete_json
        close = provider.close

        def complete(request):
            entered.set()
            assert release.wait(timeout=10)
            return original(request)

        def finish():
            close()
            completed.set()

        provider.complete_json = complete
        provider.close = finish
        return provider

    app = create_app(settings, provider_factory=factory)
    with TestClient(app) as client:
        register(client)
        job_id = create(client, brief)
        assert action(client, job_id, action="run").status_code == 202
        assert entered.wait(timeout=10)
        assert client.get(f"/api/projects/{job_id}").json()["busy"]
        assert action(client, job_id, action="run").status_code == 409
        assert action(client, job_id, action="cancel").status_code == 409
        release.set()
        lock_path = (
            settings.data_dir / "locks" / (hashlib.sha256(job_id.encode()).hexdigest() + ".lock")
        )

        def wait_done():
            assert completed.wait(timeout=15)
            with FileLock(lock_path, timeout=10):
                pass  # Wait for the worker's finally block to release the job lock.
            completed.clear()
            return client.get(f"/api/projects/{job_id}").json()

        for stage in ["plan", "sources", "outline"]:
            detail = wait_done()
            assert detail["job"]["pending_approval"] == stage
            assert action(client, job_id, action="approve", stage=stage).status_code == 202
            assert action(client, job_id, action="run").status_code == 202
        detail = wait_done()
        assert detail["job"]["status"] == "COMPLETED"
        assert set(detail["downloads"]) == {"docx", "pdf", "json"}
        assert client.get(f"/api/projects/{job_id}/downloads/pdf").content.startswith(b"%PDF")
        assert client.get(f"/api/projects/{job_id}/downloads/docx").content.startswith(b"PK")
        assert client.get(f"/api/projects/{job_id}/downloads/json").json()["package"]["demo_mode"]
        assert action(client, job_id, action="approve", stage="outline").status_code == 409
        # Even corrupt persisted file records cannot download files outside this job's export dir.
        package = app.state.store.get_artifact(job_id, Stage.OUTPUT, "output")
        package["files"][0]["path"] = str(settings.data_dir / "accounts.sqlite3")
        app.state.store.save_artifact(job_id, Stage.OUTPUT, "output", 999, package)
        assert client.get(f"/api/projects/{job_id}/downloads/docx").status_code == 404


def test_config_reports_pdf_font_readiness_before_any_work_is_spent(settings, tmp_path):
    configured = settings.data_dir / "custom.ttf"
    configured.write_bytes(b"placeholder")
    with TestClient(create_app(replace(settings, pdf_font=str(configured)))) as client:
        assert client.get("/api/config").json()["pdf_font"] == str(configured)
    with TestClient(create_app(replace(settings, pdf_font=str(tmp_path / "absent.ttf")))) as client:
        assert client.get("/api/config").json()["pdf_font"] is None
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/config").json()["pdf_font"].endswith(".ttf")


def test_ui_assets_are_served_locally_and_no_cors(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
        assert response.status_code == 200 and "/static/app.js" in response.text
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200
        response = client.options(
            "/api/projects",
            headers={
                "Origin": "https://evil.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Evidex-Request",
            },
        )
        assert "access-control-allow-origin" not in response.headers


def test_passwords_are_salted(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.register("one@example.test", PASSWORD)
    store.register("two@example.test", PASSWORD)
    with store.connection() as db:
        hashes = [r[0] for r in db.execute("SELECT password_hash FROM users")]
    assert hashes[0] != hashes[1]


def test_rejection_feedback_and_actor_are_persisted(settings, brief):
    from evidex.providers import FakeLLM
    from evidex.runner import PipelineRunner

    app = create_app(settings)
    with TestClient(app) as client:
        registered = register(client).json()
        job_id = create(client, brief)
        # Execute synchronously here to focus on HTTP checkpoint transitions.
        PipelineRunner(app.state.store, FakeLLM()).run(job_id)
        assert (
            action(client, job_id, action="reject", stage="sources", feedback="Scope").status_code
            == 409
        )
        assert (
            action(
                client, job_id, action="reject", stage="plan", feedback="Narrow the scope"
            ).status_code
            == 202
        )
        detail = client.get(f"/api/projects/{job_id}").json()
        assert detail["job"]["status"] == "NEEDS_HUMAN"
        rejection = next(e for e in detail["events"] if e["event_type"] == "approval_rejected")
        assert rejection["payload"]["actor"] == registered["id"]
        assert rejection["payload"]["feedback"] == "Narrow the scope"
        assert (
            action(client, job_id, action="retry", feedback="Focus on undergraduates").status_code
            == 202
        )
        detail = client.get(f"/api/projects/{job_id}").json()
        assert detail["job"]["status"] == "RUNNING"
        assert detail["job"]["feedback_for_retry"] == "Focus on undergraduates"
        assert action(client, job_id, action="cancel").status_code == 202
        assert client.get(f"/api/projects/{job_id}").json()["job"]["status"] == "CANCELLED"
