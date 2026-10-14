# Milestone Plan

This plan follows Section 13 of the build brief. Work proceeds in order, with tests and a runnable repository at each milestone. A milestone is complete only when its exit checks pass and the README plus `docs/decisions.md` reflect what works and what remains.

## 1. Skeleton — pipeline, persistence, gates, fake provider

**Deliverables**
- Python package and local run/test commands.
- Typed domain artifacts, an explicit closed state machine, stage order, and configurable retry/budget policies.
- SQLite persistence for jobs, versioned artifacts, attempts, gate results, model-call records, and append-only events.
- Provider protocol and deterministic fake provider; versioned prompt files.
- End-to-end stub pipeline: intake → plan → sources → outline → section writing → review → output.
- Human approval checkpoints, retry feedback, `NEEDS_HUMAN`, resume/cancel semantics, and baseline deterministic gates.
- Tests for transition guards, gate pass/fail, retry exhaustion, persistence, and a forced-failure end-to-end run.

**Exit checks**
- Full pipeline can be run locally without external credentials.
- A failed stage is retried with changed feedback; exhaustion pauses for a human.
- Invalid transitions and unregistered citations are rejected; no model output can select the next state.
- Restart/resume uses persisted state and does not repeat completed stages.

## 2. Intake and Planning — validated user request and plan approval

**Deliverables**
- `ProjectBrief` and `ResearchPlan` schemas with supported document, degree, language, style, length, methodology, and data states.
- Intake and planning prompts, provider adapter configuration, schema validation, targeted intake questions, and planning gates.
- Human plan approval and edit events.
- Environment-based provider settings, timeout/backoff, call-cost/token recording, and budget enforcement.

**Exit checks**
- Schema and gate tests cover valid/invalid, underspecified, and contradictory requests.
- Provider errors and malformed JSON retry with structured feedback and fail to `NEEDS_HUMAN` at the configured limit.
- No API key is required to use fake mode.

## 3. Source Registry and Retrieval — verified evidence

**Deliverables**
- Source, verification, and evidence-note domain records; import for BibTeX/RIS and upload extraction path.
- Deterministic deduplication, DOI/title-author-year verification, retraction checks, source/recentness/topic coverage gates, and student confirmation.
- Connectors for Crossref, OpenAlex, Semantic Scholar, arXiv, PubMed/Europe PMC, DOAJ, CORE, and Unpaywall as permitted and configured; fixture-based contract tests.
- Targeted retries for only uncovered subtopics and source-list approval UI/API.

**Exit checks**
- Unverified/retracted/duplicate records cannot silently be used as verified sources.
- API failures and coverage gaps are visible; no live network dependency exists in tests.

## 4. Outline — document templates and approval

**Deliverables**
- Article, proposal, and thesis templates with degree-specific defaults and university-template override boundary.
- Structured hierarchical outline, objective/question coverage, source assignment/drop reasons, and word-budget checks.
- Outline editor and human approval endpoint/UI; change history.

**Exit checks**
- Required sections and budgets are validated deterministically; approval is required before writing.

## 5. Section writing — claims, evidence, and isolated retries

**Deliverables**
- Ordered section worker with only section spec, assigned evidence, glossary, and concise preceding summary in context.
- Structured claim records; citation allow-list; entailment judge interface; overlap, number-tracing, word-count, language/register, and terminology gates.
- Per-section retries without restarting successful sections; student-data placeholders for findings/results.

**Exit checks**
- Fake citations, unsupported claims, untraced numbers, copied text, and invalid word budgets fail closed.
- A failing section alone is retried and all evidence is traceable in stored records.

## 6. Review — whole-document checks and code routing

**Deliverables**
- `ReviewReport`, citation/reference one-to-one and CSL checks, question/conclusion coverage, cross-reference and consistency checks, language-specific style adapters, and overlap report.
- Code-derived target-section routing, capped review cycles, and uncertainty/low-confidence reporting.

**Exit checks**
- Review failures route only to affected sections; review cannot invent a route or cause unrestricted retries.
- Review cycle exhaustion pauses for human action with a clear report.

## 7. Output — document rendering and audit package

**Deliverables**
- DOCX renderer, PDF path, optional LaTeX, BibTeX/RIS exports, citation audit report, change log, optional AI-use disclosure.
- File-open/format checks for RTL, fonts, margins, headings, TOC, pagination, citations, and configured templates.

**Exit checks**
- Output package is generated from approved artifacts; validation failure blocks completion.
- Audit links every cited claim to source and evidence, flags student-confirmed sources and overrides, and reconciles reference counts.

## 8. Web UI polish and production hardening

**Deliverables**
- Next.js Persian-first RTL UI with English locale: auth, project list/quotas, wizard, pipeline dashboard, approvals, source library, draft viewer, export page, SSE progress, cancel/resume, and `NEEDS_HUMAN` actions.
- PostgreSQL, Redis-backed worker, S3-compatible private storage, tenant isolation, deletion, rate limits, quotas, structured logging, metrics, and deployment configuration.
- Accessibility, responsive design, security review, documentation, and CI hardening.

**Exit checks**
- Complete student workflow is usable without leaving the pipeline; API/UI ownership checks protect all private artifacts.
- End-to-end CI covers forced gate failure/retry and no stage order is controlled by model output.

## Current implementation status

- **Milestone 1 — complete:** `src/evidex` pipeline core, schemas, state machine, SQLite persistence, append-only event log, attempt/artifact/gate/model-call records, versioned prompts, synthetic provider, CLI, and baseline gates are implemented. The fake pipeline completes end-to-end with explicit test approvals; forced plan and section gate failures retry with feedback, and a section retry leaves successful sections untouched. Restart/resume, retry exhaustion, review routing, overrides, invalid transitions, and each current gate are covered by tests. `pytest` passes (19 tests).
- **Milestones 2–8 — planned:** Real LLM adapter and intake/planning workflow, scholarly retrieval and source verification, outline approval interface, evidence-aware section writing, global review, rendered export package, and the Persian-first authenticated web UI/production hardening remain outstanding. See the README for exact run instructions and the synthetic-only warning.
