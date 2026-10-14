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

## Integration/workspace increment (2026-10-14)

| ID | Decision | Rationale / consequence |
|---|---|---|
| D-011 | Ship a same-origin static fa/en workspace with FastAPI instead of introducing Next.js now. | Supersedes the initial UI sequencing in D-004. One Python install runs the complete workspace; no Node build, cross-origin token storage, or client-side provider secrets. |
| D-012 | Use OpenAI-compatible Chat Completions JSON mode for generative stages only. | Existing provider protocol and gates stay authoritative. Intake, registry provenance, dataset placeholders, and filesystem output remain application code. |
| D-013 | Integrate Crossref first, with individual DOI lookups and deposited abstracts as explicitly labeled verbatim evidence. | No claim of full-text access or exhaustive retraction/semantic verification. Missing abstracts and insufficient coverage fail closed. Other scholarly providers remain roadmap items. |
| D-014 | Use scrypt credentials and revocable hashed opaque sessions in a local account database. | Avoids persistent bearer tokens in browser storage; per-owner access checks apply to every project action and download. HTTPS/Secure cookies are default; recovery, MFA, and email verification remain future work. |
| D-015 | Use a bounded in-process thread pool and per-job filesystem locks over the resumable runner. | Queue acceptance is not durable and resumes after restart are manual. This is local execution infrastructure, not a substitute for D-009's future distributed worker. |
| D-016 | Render DOCX with python-docx and PDF with fpdf2 + HarfBuzz + a Unicode TTF font. | No LibreOffice service required; Arabic/Persian shaping supported. Style-compliant CSL, TOC, custom university templates, and exact pagination are explicitly not promised. |
| D-017 | Persist project demo/live mode and require live AI disclosure. | Restart cannot silently insert fixtures into a live project; demo web exports remain labeled synthetic. Original CLI fixture demo stays non-rendering for compatibility. |
| D-018 | Package prompts alongside Python code. | Moves canonical versioned files to `src/evidex/prompts/`; installed wheels work outside the Git checkout. |

| D-019 | Report application/provider stage failures (`stage_executed`, gate `<stage>.execution`) separately from model-output schema failures (`schema_valid`), and never treat an empty payload as model output. | Rendering, intake normalization, dataset placeholders, and retrieval are application code: a failure there cannot be fixed by asking the model to regenerate, and the previous wording blamed the student for a 2-field `ExportPackage` validation error while discarding the real exception from the attempt record. `stage_executed` failures are also excluded from human overrides because there is no output to attest. |
| D-020 | Discover the PDF font at render time from a candidate list when `EVIDEX_PDF_FONT` is unset, and expose the resolved path in `GET /api/config`. | The hard-coded DejaVu path made export fail on macOS, Windows, and slim containers after all approvals were already spent. An explicitly configured path is still never silently replaced. |

This increment adds working baseline integrations across milestones 2–8, not completion of every roadmap deliverable. Tests use injected HTTP mocks; actual external API access depends on deployment network permissions and configured credentials. Authentication, rendered output, and the browser flow are independently runnable in explicit demo mode.
