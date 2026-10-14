# Evidex architecture

## Implemented system

```text
Browser: static fa/en workspace, RTL, same-origin fetch + polling
  │ session cookie / HTTPS
FastAPI: auth, private projects, actions, artifacts, downloads
  ├── Account store: scrypt hashes, hashed opaque sessions, ownership, rate limits
  ├── Job-level filesystem lock + bounded local thread pool
  └── PipelineRunner: fixed state graph, gates, retries, human checkpoints
        ├── Intake: application validation (not model normalization)
        ├── Plan / outline / writing / review: OpenAI-compatible JSON adapter
        ├── Sources: Crossref search → individual DOI lookup → deposited abstracts
        └── Output: code-owned DOCX + PDF + JSON audit renderer
  │
SQLite: job states, artifacts, attempts, gate/model records, append-only events
Local private storage: exports and per-job locks
```

Python 3.11+ is the baseline. The UI intentionally has no frontend build dependency; the assets and prompts ship inside the wheel. Next.js, PostgreSQL, distributed queues, and object storage remain future options, not currently required services.

## Workflow/control boundary

The ordered stages remain **intake → plan → sources → outline → writing → review → output**. Plan, sources, and outline pause for authenticated human approval. Rejecting an artifact pauses it for feedback and a human retry. Gate failures persist before retrying; exhaustion yields `NEEDS_HUMAN`.

Gate failures distinguish *model output that failed validation* from *a stage that could not run*. A schema failure (`schema_valid`, gate `<stage>.schema`) quotes the validator errors and asks for a regenerated stage. When application code or the provider raises (rendering, retrieval, a rejected HTTP call), no payload exists to validate: the runner records the attempt as `provider_error` with the real message, saves no artifact, and fails the `stage_executed` check (gate `<stage>.execution`) with that cause. Execution failures cannot be waived by a human override because there is nothing to attest, and the retry feedback never asks the student to regenerate model text that was never produced. The model never picks the next stage, approves a checkpoint, overrides a check, creates files, or assigns verification status.

Writing runs one outline node at a time. Review findings route through the existing code-owned section retry mechanism. Results/findings without an uploaded dataset are code-generated placeholders in live mode, including when the brief says the student has data. There is no upload implementation yet.

`IntegratedProvider` implements the existing provider protocol as a stage dispatcher. Intake, source retrieval, and output return application results under their own service names with zero model tokens. Generative stages use `OpenAIProvider`. Every response still passes the runner's Pydantic schema and deterministic gate. Demo mode uses `FakeLLM` only when explicitly selected. Project execution mode is persisted and checked on resume.

## External integrations

### LLM

The adapter sends the stage's packaged versioned prompt, Pydantic JSON schema, template/budgets, stage input, and prior gate feedback to `/chat/completions` in JSON-object mode. It validates returned JSON before returning it to the runner. Model text and third-party abstracts are untrusted data. No tools, shell execution, or model-selected URLs are offered.

HTTPS endpoints and keys are server configuration only. Requests use timeouts, at most three transport attempts with exponential backoff for network failures/429/5xx, and stable attempt idempotency headers. Other HTTP errors are not retried at the transport layer. Error records omit remote bodies and credentials. Stage retries remain owned by the runner. Token usage and latency are recorded when available; dollar cost is unknown, not invented. A per-call 12,000-output-token cap is not a global cost budget.

### Crossref

Searches combine the approved topic and each subtopic. Candidates receive individual DOI metadata lookups. The adapter creates stable hash-based source/note IDs, preserves author/title/date/venue/DOI metadata, deduplicates DOIs, detects retraction indicators exposed in that metadata, and stores publisher-deposited abstract text verbatim with an explicit abstract-only locator. There is no LLM-generated citation registry or invented evidence paraphrase.

A record must have a matching DOI, title, authors, publication year, and abstract to become usable. Known retractions remain visible and fail the gate. The registry's `verified` status means **metadata retrieved at that DOI**, not semantic entailment or comprehensive retraction assurance. Search matches are provisional relevance candidates; students approve them. Insufficient counts/coverage/recency fail rather than padding the registry. Existing gates are not relaxed for real providers.

Retrieval is bounded (12 subtopics, 30 search hits/subtopic, 150 individual DOI lookups/attempt). Source retries currently repeat the approved-plan search; there is no source editing/import or semantic relevance ranking. The `EvidenceNote.paraphrase` legacy schema field contains explicitly labeled verbatim abstracts in this adapter.

## Authentication/privacy boundary

`accounts.sqlite3` stores users, independent scrypt salts/hashes, hashed random session tokens, expiry timestamps, persistent rate limits, and account/job ownership. Seven-day sessions use HttpOnly + SameSite=Strict cookies, Secure by default. Logout revokes the server session; sign-in replaces the caller's existing session. Unknown accounts take a dummy scrypt path during login. Validation responses do not echo passwords.

All browser mutations, including login, require a custom same-origin header. Cross-site Fetch Metadata requests are rejected; CORS is not enabled. The API takes approval actors from the session. Project lists, details, actions, and each download check ownership; another user's job returns 404. Artifact text is escaped before DOM insertion. A restrictive script/style CSP, no-store responses, and MIME-sniffing protection apply. Files are not mounted as static content.

Only the authenticated owner can download completed-job records, with an additional resolved-path check under that job's hashed export directory. Remote/model text cannot choose a path. The CLI and direct local filesystem access are trusted operator capabilities, outside the web authentication boundary.

## Concurrency/durability

Two local worker threads run at most four accepted jobs (running plus queued). Each job's web actions acquire a filesystem lock shared across local processes, preventing overlapping runs/approvals/cancellation. For deployment, use one server process and a local filesystem with functioning locks. The CLI must not operate concurrently on a web-owned job.

SQLite persists progress independently of the thread pool. The worker queue itself is **not durable**. After restart, the owner resumes jobs manually from the last persisted stage/attempt. Exactly-once remote billing cannot be guaranteed if a worker crashes between the external call and persistence. Job creation and account ownership use separate SQLite databases; a failure between writes can leave an inaccessible orphan job, never a public one. A production transactional service should unify these boundaries.

Cancellation currently requires the run lock to be free. It does not interrupt an external request mid-stage. API responses are nonblocking for runs (202); the UI polls progress. Failed/unexpected worker exceptions are logged and the last durable state remains resumable.

## Rendering

The renderer consumes ordered, reviewed sections, the approved registry, and recorded overrides. It resolves only audited citation IDs, builds draft references and per-source claim/note mappings, and creates:

- DOCX via `python-docx`, with paragraph/run RTL properties and Unicode font selection.
- PDF via `fpdf2`, an embedded Unicode font, and HarfBuzz shaping. `EVIDEX_PDF_FONT` names the font explicitly; otherwise an installed DejaVu/Noto/Vazirmatn/system font is discovered, and `GET /api/config` reports the resolved path (or `null`) so a missing font is visible before export work is approved.
- JSON with the citation audit, registry, sections, review, disclosure, and overrides.

Temporary files are rendered inside a job-specific directory, then atomically replaced individually. Incomplete attempts cannot be downloaded through the API. File sizes come from disk, never model assertions. Live output must include a disclosure and both document formats; the gate checks metadata and audit completeness. Documents are drafts: exact CSL style compliance, automatic TOC, university layouts, and DOCX/PDF pagination parity remain future work.

## Tests and deployment boundaries

The original core tests remain. Additional tests cover OpenAI request/schema/usage/error contracts, Crossref normalization/missing evidence/retraction behavior, mocked live end-to-end output, a render failure surfacing its cause instead of an `ExportPackage` schema error, font discovery/override behavior, actual DOCX opening/PDF parsing (English and Persian), account isolation, session revocation/expiry, CSRF, login throttling, concurrent-run rejection, approval/download workflow, and path confinement. No test needs live credentials or live scholarly content. Manual browser smoke checks cover account creation, all three approvals, exports, and RTL mobile layout.

Before a public service, implement global token/cost budgets, stronger semantic/evidence checking, verified identities/recovery/MFA, durable distributed queues, backups/deletion/retention, monitoring, and production storage. Do not describe the current system as verified academic correctness or production-hardened SaaS.
