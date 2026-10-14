from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from evidex.models import (
    CitationStyle,
    DataSituation,
    DegreeLevel,
    DocumentType,
    JobStatus,
    Language,
    ProjectBrief,
    Stage,
)
from evidex.providers import FakeLLM
from evidex.runner import PipelineRunner
from evidex.store import SQLiteStore


def _database(path: str) -> SQLiteStore:
    return SQLiteStore(Path(path).expanduser())


def _print(value: object) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _demo(args: argparse.Namespace) -> int:
    store = _database(args.database)
    try:
        language = Language(args.language)
        topic = args.topic or (
            "رابطه حمایت اجتماعی با سلامت روان دانشجویان"
            if language == Language.PERSIAN
            else "How social support relates to university student mental health"
        )
        brief = ProjectBrief(
            document_type=DocumentType(args.document_type),
            degree_level=DegreeLevel(args.degree_level),
            field=args.field,
            topic=topic,
            language=language,
            citation_style=CitationStyle(args.citation_style),
            target_words=args.target_words,
            methodology=args.methodology,
            data_situation=DataSituation(args.data_situation),
        )
        runner = PipelineRunner(store, FakeLLM(fail_first_stages=set(args.fail_first or [])))
        state = runner.create_project(brief)
        print(f"Created demonstration job {state.job_id}")
        for _ in range(20):
            state = runner.run(state.job_id)
            if state.status == JobStatus.AWAITING_APPROVAL and args.auto_approve:
                assert state.pending_approval is not None
                state = runner.approve(
                    state.job_id, state.pending_approval, actor="explicit-demo-auto-approval"
                )
                continue
            if state.status in {
                JobStatus.AWAITING_APPROVAL,
                JobStatus.NEEDS_HUMAN,
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                break
        attempts = store.list_attempts(state.job_id)
        events = store.list_events(state.job_id)
        _print(
            {
                "job_id": state.job_id,
                "status": state.status.value,
                "current_stage": state.current_stage.value if state.current_stage else None,
                "pending_approval": state.pending_approval.value
                if state.pending_approval
                else None,
                "attempts": [
                    {key: item[key] for key in ("stage", "task_key", "attempt", "status")}
                    for item in attempts
                ],
                "failed_gate_events": [
                    event["payload"] for event in events if event["event_type"] == "gate_failed"
                ],
                "event_count": len(events),
                "artifact_count": len(store.list_artifacts(state.job_id)),
                "model_call_count": len(store.list_model_calls(state.job_id)),
                "warning": "Synthetic fixtures only; this demo is not a scholarly source-backed draft and exports no document.",
            }
        )
        return 0 if state.status in {JobStatus.COMPLETED, JobStatus.AWAITING_APPROVAL} else 1
    finally:
        store.close()


def _run(args: argparse.Namespace) -> int:
    store = _database(args.database)
    try:
        from evidex.runtime import Settings, make_provider

        mode = store.get_job(args.job_id).data.get("execution_mode", "demo")
        provider = make_provider(Settings.from_env(), demo=False) if mode == "live" else FakeLLM()
        try:
            state = PipelineRunner(store, provider).run(args.job_id)
        finally:
            if hasattr(provider, "close"):
                provider.close()
        _print(state)
        return 0
    finally:
        store.close()


def _approve(args: argparse.Namespace) -> int:
    store = _database(args.database)
    try:
        state = PipelineRunner(store).approve(args.job_id, Stage(args.stage), actor=args.actor)
        _print(state)
        return 0
    finally:
        store.close()


def _status(args: argparse.Namespace) -> int:
    store = _database(args.database)
    try:
        state = store.get_job(args.job_id)
        attempts = store.list_attempts(args.job_id)
        events = store.list_events(args.job_id)
        _print(
            {
                "job": state.model_dump(mode="json"),
                "attempts": [
                    {key: item[key] for key in ("stage", "task_key", "attempt", "status", "error")}
                    for item in attempts
                ],
                "gate_failures": [
                    event["payload"] for event in events if event["event_type"] == "gate_failed"
                ],
                "event_count": len(events),
                "artifact_index": [
                    {key: item[key] for key in ("stage", "task_key", "version", "created_at")}
                    for item in store.list_artifacts(args.job_id)
                ],
            }
        )
        return 0
    finally:
        store.close()


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from evidex.runtime import Settings, load_env_file

    env_file = load_env_file()  # Real environment variables still take precedence.
    if args.demo:
        os.environ["EVIDEX_DEMO"] = "1"
    if args.insecure_cookies:
        os.environ["EVIDEX_SECURE_COOKIES"] = "0"
    settings = Settings.from_env(load_dotenv=False)
    print(
        f"Config: {env_file or 'no .env file found (using process environment only)'}",
        flush=True,
    )
    if settings.demo:
        print("Mode: DEMO (synthetic fixtures; no LLM or Crossref calls).", flush=True)
        if settings.llm_key:
            print(
                "Note: EVIDEX_LLM_API_KEY is set but ignored because demo mode is on. "
                "Remove --demo and EVIDEX_DEMO=1 to use the configured LLM.",
                flush=True,
            )
    elif settings.llm_key:
        print(f"Mode: LIVE (model {settings.llm_model} via {settings.llm_base_url}).", flush=True)
    else:
        print(
            "Mode: LIVE, but EVIDEX_LLM_API_KEY is not set; project creation will be refused. "
            "Set it in .env or pass --demo for the synthetic demo.",
            flush=True,
        )
    uvicorn.run("evidex.api:create_app", factory=True, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidex", description="Auditable academic-writing pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the authenticated web workspace and API")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--demo", action="store_true", help="Use visibly synthetic fixtures")
    serve.add_argument(
        "--insecure-cookies", action="store_true", help="Local HTTP only; never public"
    )
    serve.set_defaults(func=_serve)

    demo = subparsers.add_parser("demo", help="Run the synthetic fixture pipeline")
    demo.add_argument("--database", default=".evidex/evidex.sqlite3")
    demo.add_argument(
        "--auto-approve",
        action="store_true",
        help="Explicitly simulate human approvals for demo only",
    )
    demo.add_argument("--language", choices=[item.value for item in Language], default="en")
    demo.add_argument(
        "--document-type", choices=[item.value for item in DocumentType], default="proposal"
    )
    demo.add_argument("--degree-level", choices=[item.value for item in DegreeLevel], default="bsc")
    demo.add_argument("--field", default="Social sciences")
    demo.add_argument("--topic")
    demo.add_argument("--target-words", type=int, default=3000)
    demo.add_argument("--methodology", default="Scoping literature review")
    demo.add_argument(
        "--data-situation", choices=[item.value for item in DataSituation], default="no_data"
    )
    demo.add_argument(
        "--citation-style",
        choices=[item.value for item in CitationStyle if item != CitationStyle.CUSTOM],
        default="apa7",
    )
    demo.add_argument(
        "--fail-first",
        action="append",
        choices=[stage.value for stage in Stage],
        help="Force a first-attempt gate failure to demonstrate retries",
    )
    demo.set_defaults(func=_demo)

    run = subparsers.add_parser("run", help="Resume a persisted job until its next checkpoint")
    run.add_argument("job_id")
    run.add_argument("--database", default=".evidex/evidex.sqlite3")
    run.set_defaults(func=_run)

    approve = subparsers.add_parser("approve", help="Approve the current human checkpoint")
    approve.add_argument("job_id")
    approve.add_argument("stage", choices=[stage.value for stage in Stage])
    approve.add_argument("--actor", default="student")
    approve.add_argument("--database", default=".evidex/evidex.sqlite3")
    approve.set_defaults(func=_approve)

    status = subparsers.add_parser(
        "status", help="Inspect persisted state, attempts, artifacts, and events"
    )
    status.add_argument("job_id")
    status.add_argument("--database", default=".evidex/evidex.sqlite3")
    status.set_defaults(func=_status)
    return parser


def main() -> None:
    from evidex.runtime import load_env_file

    load_env_file()
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
