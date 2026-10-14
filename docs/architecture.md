# Evidex Architecture

## Purpose and constraints

Evidex is a Persian-first, bilingual academic-writing workspace for articles, proposals, and theses. It creates a source-backed draft through an auditable, resumable pipeline. The application assists with structure and prose; it does not invent research data, findings, interviews, or references. Students approve the plan, sources, and outline, and remain responsible for supplied data and final content.

The non-negotiable control boundary is that **application code owns stage order, transitions, retries, approvals, and routing**. A language model can only return one stage-specific structured artifact. Its output can never advance the state machine or pass a gate.

## System shape

The system is organized as a domain-focused backend, a thin web/API layer, and a client UI:

```text
Next.js (fa/en, RTL-first)
        │ HTTPS / SSE
FastAPI API ─────────────── Auth, projects, approvals, artifacts, downloads
        │
Pipeline application service ─── fixed stage graph, retry policy, budgets
        ├── stage workers ─────── narrow task + versioned prompt + schema
        ├── deterministic gates ─ pure checks; semantic checks fail closed
        ├── provider adapters ─── Fake provider first; real providers later
        ├── source registry ───── retrieval, verification, evidence notes
        └── document renderer ─── DOCX first, PDF/LaTeX later
        │
SQLite (local development) / PostgreSQL (deployment)
Append-only job events + versioned artifacts + attempts + gate/model-call records
        │
Worker queue: local resumable runner first; Redis + RQ/Celery when deployed
Object storage: local development; S3-compatible storage when deployed
```

The repository was initially empty. Milestone 1 is backend-first so the core workflow, persistence contract, and tests can be validated before UI or external services are introduced. At this milestone, the runnable interface is a CLI; the API and browser UI in the diagram are planned for later increments. Python 3.11 is the compatibility baseline for this checkout; code should remain compatible with 3.12. The target API uses FastAPI and Pydantic v2. SQLite is a local-development adapter, not the intended multi-user production database.

## Domain and pipeline boundaries

### Explicit workflow

The orchestrator owns a fixed ordered workflow:

1. Intake (`ProjectBrief`)
2. Planning (`ResearchPlan`)
3. Source gathering (`SourceRegistry`)
4. Outline (`DocumentOutline`)
5. Writing (one `SectionDraft` per outline node, in deterministic order)
6. Review (`ReviewReport`)
7. Output (`ExportPackage`)

Each stage is implemented behind a narrow service interface and produces a versioned, Pydantic-validated artifact. A `Gate` receives the artifact and persisted job context and returns `GateResult` (`gate_id`, stage, passed, checks, retry feedback, optional code-selected route targets). Deterministic checks run before any semantic judge. A failed gate retries only that stage (or, during review, only code-routed sections), with the prior structured feedback included in the next attempt. Exhaustion moves the job to `NEEDS_HUMAN`; no silent fallback or automatic acceptance is allowed.

Human checkpoints are explicit transitions to `AWAITING_APPROVAL` after planning, source gathering, and outline generation. Approvals, edits, retries, overrides, cancellations, and resumes are recorded as events. A human override never deletes a failed check and is included in the audit trail.

### State and durability

The state machine has a closed set of job and stage states: `PENDING`, `RUNNING(stage, attempt)`, `GATE_PASSED`, `GATE_FAILED`, `AWAITING_APPROVAL`, `NEEDS_HUMAN`, `COMPLETED`, `FAILED`, and `CANCELLED`. Only orchestrator transition functions may change state. State changes and append-only events are committed together. Stage attempts and artifacts are addressed by job, stage, and attempt/version so a worker restart can identify completed work and avoid duplicating it. Side effects (retrieval, rendering, model calls) use idempotency keys where their adapters permit them.

Every model call records prompt name/version, provider/model, request and response schema versions, token/cost/latency fields when available, outcome, and timestamps. Local fake calls use the same record format. Per-job token, cost, and wall-clock budgets belong to the orchestrator's execution policy and will fail closed; Milestone 1 records stub usage but does not yet enforce global limits.

### LLM boundary and prompts

A provider-agnostic adapter accepts a stage-specific request and returns JSON. The returned JSON is parsed against the stage's Pydantic schema; malformed output is a failed attempt. The initial implementation provides a deterministic fake provider for fixtures and end-to-end tests. Real-provider adapters, timeouts, backoff, caching, and cost accounting are added behind the same interface. Prompt text is versioned under `prompts/<stage>/` and prompt version is recorded per call; business logic, gates, and transition decisions remain ordinary Python code.

### Citation and evidence integrity

The source registry is the only citation authority. Every source has stable registry and note IDs, origin, metadata, verification status/method, checked timestamp, retraction state, relevance, and paraphrased evidence notes with locators. The writer can only reference registry IDs; citation-shaped free text not backed by a source is rejected. DOI sources are checked against Crossref and must meet deterministic title, author, and year matching rules; sources without DOI are matched against supported scholarly registries. Unverifiable imports remain visibly unverified until confirmed by the student and are flagged in the audit report.

Each factual claim is represented as a structured record with source IDs and evidence-note IDs. Unsupported/partial entailment, excessive overlap, untraced numbers, or invalid citation IDs fail the section gate. Results remain explicit `[STUDENT_DATA: ...]` placeholders unless the student supplies data or deterministic analysis output. Retrieval adapters are added incrementally and only use official APIs or permitted access methods; Persian sources without a permitted API are imported by the student.

### Persistence and interfaces

The local adapter uses SQLite for zero-service development and crash/restart testing. The persistence interface isolates this choice so deployment can use PostgreSQL without changing the domain/orchestrator layer. A worker is always a separate application service even when run locally in-process; the deployed adapter will use Redis with RQ or Celery. User uploads/exports are private per owner, stored outside version control, and exposed only through authorized API routes. The production deployment uses encrypted database/object storage, strict tenant scoping, deletion workflows, rate limits, and secret configuration from the environment.

The API exposes project creation, run/resume/cancel, event/progress streaming (SSE), artifact inspection/editing, approvals, source imports, and export downloads. The Next.js app is RTL-first with Persian as default and English as a second locale. The UI visualizes every stage, attempt, gate check, approval, failure, and retry; it never decides workflow transitions.

## Output and review

Output rendering consumes persisted, approved artifacts only. DOCX is the primary deliverable; PDF and optional LaTeX follow. References are formatted through CSL rather than model prose. The package includes BibTeX/RIS where possible, a citation audit mapping sources to claims/evidence, an override/change log, a review report, and an optional AI-use disclosure. RTL direction, mixed-script punctuation/digits, fonts, page layout, references, and document validity are checked before completion.

## Security, privacy, and observability

- Enforce user/project ownership at every API and storage boundary; never place another user's content in a prompt.
- Sanitize imports and validate file type/size; treat extracted content as untrusted input.
- Keep credentials out of source control and redact secrets/PII from structured logs.
- Support cancellation, deletion, quotas, and per-job budgets.
- Record structured job/stage IDs, retries, gate outcomes, model usage, cost, and latency; expose operational metrics without exposing document contents.

## Test strategy

- Unit tests for schemas, transition legality, deterministic gates, retry budgets, and event persistence.
- Connector contract tests against recorded fixtures; no live scholarly API required in CI.
- End-to-end test using the fake provider, including a deliberately bad artifact, feedback-based retry, human checkpoint approval, full completion, and restart/resume behavior.
- Golden prompt/schema fixtures and export validation tests as those milestones are implemented.
- Run the test suite after each milestone; keep the local skeleton runnable without external credentials or services.

## Blocking questions

None currently. The brief supplies workable product, workflow, and stack defaults. Decisions that can be made safely are recorded in `docs/decisions.md`; external provider credentials and a university-specific template are optional configuration, not blockers to the initial skeleton.
