from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, field_validator

from evidex.auth import SESSION_SECONDS, AuthStore
from evidex.models import JobStatus, ProjectBrief, Stage
from evidex.rendering import DocumentRenderer
from evidex.runner import PipelineRunner
from evidex.runtime import Settings, make_provider
from evidex.store import SQLiteStore

log = logging.getLogger(__name__)
COOKIE = "evidex_session"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class Action(BaseModel):
    action: Literal["run", "approve", "reject", "retry", "cancel"]
    stage: Stage | None = None
    feedback: str = Field(default="", max_length=4000)


def create_app(settings: Settings | None = None, provider_factory=make_provider) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(settings.data_dir / "evidex.sqlite3")
    auth = AuthStore(settings.data_dir / "accounts.sqlite3")
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="evidex")
    slots = BoundedSemaphore(4)  # Two running + two queued runs, not an unbounded paid-work queue.
    locks_dir = settings.data_dir / "locks"
    locks_dir.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(app):
        yield
        pool.shutdown(wait=True)
        store.close()

    app = FastAPI(title="Evidex", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.auth = store, auth

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default includes invalid input values, potentially passwords.
        return JSONResponse(
            {
                "detail": [
                    {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.middleware("http")
    async def security(request: Request, call_next):
        # A custom header is required even for login/register to prevent login CSRF.
        # No CORS middleware: foreign origins cannot pass the preflight.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("x-evidex-request") != "1":
                return JSONResponse(
                    {"detail": "Missing same-origin request header"}, status_code=403
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'"
        )
        return response

    def user(request: Request):
        current = auth.user(request.cookies.get(COOKIE, ""))
        if not current:
            raise HTTPException(401, "Sign in to continue")
        return current

    def ownership(job_id: str, current: dict):
        owned = auth.owned(job_id, current["id"])
        if not owned:
            raise HTTPException(404, "Project not found")
        return owned

    def sign_in(current: dict, request: Request, response: Response):
        auth.logout(request.cookies.get(COOKIE, ""))
        response.set_cookie(
            COOKIE,
            auth.session(current["id"]),
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            path="/",
        )
        return current

    @app.get("/api/config")
    def config():
        # Rendering is application code, so a missing PDF font is knowable before any
        # approved work is spent. Null here means exports will fail at the output stage.
        renderer = DocumentRenderer(settings.data_dir / "exports", settings.pdf_font)
        try:
            pdf_font: str | None = str(renderer.pdf_font())
        except ValueError:
            pdf_font = None
        return {
            "demo": settings.demo,
            "configured": settings.demo or bool(settings.llm_key),
            "registration": settings.registration,
            "pdf_font": pdf_font,
        }

    @app.post("/api/auth/register", status_code=201)
    def register(credentials: Credentials, request: Request, response: Response):
        if not settings.registration:
            raise HTTPException(403, "Registration is disabled")
        host = request.client.host if request.client else "unknown"
        if not auth.allow_attempt("register:" + host, limit=10):
            raise HTTPException(429, "Too many registration attempts. Try again in 15 minutes.")
        try:
            current = auth.register(credentials.email, credentials.password)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Unable to register this email; try signing in") from None
        return sign_in(current, request, response)

    @app.post("/api/auth/login")
    def login(credentials: Credentials, request: Request, response: Response):
        host = request.client.host if request.client else "unknown"
        if not auth.allow_attempt("login-email:" + credentials.email) or not auth.allow_attempt(
            "login-ip:" + host, limit=50
        ):
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
        current = auth.login(credentials.email, credentials.password)
        if not current:
            raise HTTPException(401, "Invalid email or password")
        return sign_in(current, request, response)

    @app.get("/api/auth/me")
    def me(current=Depends(user)):
        return current

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        auth.logout(request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE, path="/")

    @app.get("/api/projects")
    def projects(current=Depends(user)):
        result = []
        for row in auth.projects(current["id"]):
            state = store.get_job(row["job_id"])
            result.append(
                {"job": state, "brief": store.get_input(row["job_id"]), "demo": bool(row["demo"])}
            )
        return result

    @app.post("/api/projects", status_code=201)
    def create(brief: ProjectBrief, current=Depends(user)):
        if not settings.demo and not settings.llm_key:
            raise HTTPException(503, "Live mode needs EVIDEX_LLM_API_KEY; no demo fallback is used")
        if not auth.allow_attempt("create:" + current["id"], limit=20, window=3600):
            raise HTTPException(429, "Project creation limit reached. Try later.")
        # No model call on creation. Ownership is always checked before exposing a job.
        import uuid

        state = store.create_job(
            brief, str(uuid.uuid4()), data={"execution_mode": "demo" if settings.demo else "live"}
        )
        auth.assign(state.job_id, current["id"], settings.demo)
        return state

    def lock_for(job_id: str):
        return FileLock(
            locks_dir / (hashlib.sha256(job_id.encode()).hexdigest() + ".lock"), thread_local=False
        )

    @app.get("/api/projects/{job_id}")
    def project(job_id: str, current=Depends(user)):
        owned = ownership(job_id, current)
        lock = lock_for(job_id)
        try:
            lock.acquire(timeout=0)
        except Timeout:
            busy = True
        else:
            busy = False
            lock.release()
        state = store.get_job(job_id)
        output = store.get_artifact(job_id, Stage.OUTPUT, "output")
        return {
            "job": state,
            "brief": store.get_input(job_id),
            "demo": bool(owned["demo"]),
            "busy": busy,
            "artifacts": store.list_artifacts(job_id),
            "events": store.list_events(job_id),
            "attempts": store.list_attempts(job_id),
            "downloads": [f["format"] for f in output.get("files", [])]
            if output and state.status == JobStatus.COMPLETED
            else [],
        }

    def background_run(job_id, provider, lock):
        try:
            PipelineRunner(store, provider).run(job_id)
        except Exception:
            # Do not leak secrets in HTTP responses. The persisted state can be resumed.
            log.exception("Pipeline worker failed for job %s", job_id)
        finally:
            try:
                provider.close()
            finally:
                lock.release()
                slots.release()

    @app.post("/api/projects/{job_id}/actions", status_code=202)
    def action(job_id: str, body: Action, current=Depends(user)):
        owned = ownership(job_id, current)
        if body.action in {"reject", "retry"} and not body.feedback.strip():
            raise HTTPException(422, "Feedback is required")
        lock = lock_for(job_id)
        try:
            lock.acquire(timeout=0)
        except Timeout:
            raise HTTPException(
                409, "Project is already running; wait for the current run"
            ) from None
        provider = None
        handed_off = False
        reserved_slot = False
        try:
            if body.action == "run":
                reserved_slot = slots.acquire(blocking=False)
                if not reserved_slot:
                    raise HTTPException(429, "Worker capacity reached. Try again shortly.")
                if not auth.allow_attempt("run:" + current["id"], limit=30, window=3600):
                    raise HTTPException(429, "Run limit reached. Try later.")
                try:
                    provider = provider_factory(settings, demo=bool(owned["demo"]))
                except ValueError as exc:
                    raise HTTPException(503, str(exc)) from None
                pool.submit(background_run, job_id, provider, lock)
                handed_off = True
            else:
                # These methods perform only state transitions, not model calls.
                runner = PipelineRunner(store)
                if body.action == "approve":
                    if body.stage is None:
                        raise HTTPException(422, "Approval stage is required")
                    runner.approve(job_id, body.stage, actor=current["id"])
                elif body.action == "reject":
                    if body.stage is None:
                        raise HTTPException(422, "Rejection stage is required")
                    runner.reject_approval(job_id, body.stage, body.feedback, actor=current["id"])
                elif body.action == "retry":
                    runner.request_retry(job_id, body.feedback, actor=current["id"])
                elif body.action == "cancel":
                    runner.cancel(job_id, actor=current["id"])
            return {"accepted": True}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        finally:
            if not handed_off:
                if reserved_slot:
                    slots.release()
                if provider:
                    provider.close()
                lock.release()

    @app.get("/api/projects/{job_id}/downloads/{format}")
    def download(job_id: str, format: Literal["docx", "pdf", "json"], current=Depends(user)):
        ownership(job_id, current)
        if store.get_job(job_id).status != JobStatus.COMPLETED:
            raise HTTPException(409, "Exports are available only after completion")
        package = store.get_artifact(job_id, Stage.OUTPUT, "output") or {}
        record = next((f for f in package.get("files", []) if f["format"] == format), None)
        if not record:
            raise HTTPException(404, "Export not found")
        root = (
            settings.data_dir / "exports" / hashlib.sha256(job_id.encode()).hexdigest()
        ).resolve()
        path = Path(record["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "Export not found")
        media = {
            "pdf": "application/pdf",
            "json": "application/json",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        return FileResponse(path, media_type=media[format], filename=f"evidex-{job_id}.{format}")

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web / "index.html")

    return app
