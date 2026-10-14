# Architecture Decisions

This log records defaults chosen where the build brief leaves room for implementation judgment. Revisit decisions when deployment requirements or user research provide a concrete reason.

## Baseline decisions

| ID | Decision | Rationale / consequence |
|---|---|---|
| D-001 | Use Python 3.11 as the minimum runtime and keep code compatible with 3.12. | The available checkout runtime is Python 3.11.2; the brief's suggested 3.12 is therefore treated as a compatible target rather than a hard runtime requirement. |
| D-002 | Use FastAPI and Pydantic v2 for API contracts and structured stage artifacts. | Matches the brief and provides explicit schema validation at every model boundary. |
| D-003 | Start with SQLite as the local persistence adapter; isolate persistence behind a repository interface, with PostgreSQL as the deployment target. | A clone should run and test without external services. SQLite still exercises durable state, event history, and crash/resume semantics; production multi-user use requires PostgreSQL. |
| D-004 | Build the backend workflow before the Next.js interface. | The explicit state machine, schemas, audit model, and gates are the core safety boundary; the UI must reflect them rather than become a second orchestrator. The UI is planned for Milestone 8. |
| D-005 | Use a deterministic fake LLM and fixture source connector as the initial default; do not require provider keys or live scholarly APIs in tests. | Ensures reproducible end-to-end tests and an offline runnable skeleton. Real providers/connectors are additive adapters. |
| D-006 | Treat human approvals at plan, source, and outline checkpoints as required persisted events; tests may use an explicit approval fixture. | A stub/test flow must not imply that a production student approval was obtained. |
| D-007 | Use an append-only event table alongside normalized current job state and immutable artifact/attempt records. | Supports auditable operation and efficient current-state queries while keeping history durable. All updates that affect state are transactionally paired with events. |
| D-008 | Keep output and user-upload storage local/outside Git in development; plan for private S3-compatible object storage in deployment. | Prevents accidental publication of student material and keeps large/sensitive artifacts out of the repository. |
| D-009 | Use a local resumable worker runner first; provide a worker interface for later Redis-backed RQ/Celery deployment. | Avoids requiring Redis for the skeleton while preserving a separate job-execution boundary. An in-process web background task alone is not considered durable. |
| D-010 | No blocking product questions are open for Milestone 1. | University templates, provider credentials, and a production identity provider are optional integrations and can be configured later. |

## Milestone notes

- **Milestone 1 — complete:** Added the `src/evidex` Python package, Pydantic v2 contracts, a fixed-order resumable runner, SQLite event/artifact/attempt storage, versioned prompts, deterministic gates, a synthetic-only `FakeLLM`, and the `evidex` CLI. Verified with `pytest` (19 tests). The first increment intentionally has no browser UI, real provider adapter, external source connector, or rendered DOCX/PDF. Fixture references are separately typed and permitted only when the provider is in fixture mode; all demo packages carry `demo_mode=true` and no files.
- **Operational commands:** `pip install -e '.[dev]'`, `pytest`, `evidex demo --auto-approve --fail-first plan`, `evidex run`, `evidex approve`, and `evidex status`.
- Later milestones must append numbered decisions when a choice affects contracts, privacy, source access, or output behavior.
