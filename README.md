# Evidex

An evidence-first, Persian/English academic-writing workspace. Application code owns the pipeline, retries, gates, and approvals. Models cannot approve their own output or invent source-registry records.

## What works

- **Live LLM integration:** OpenAI Chat Completions and compatible HTTPS APIs, JSON schema validation, bounded HTTP retries, timeouts, usage/latency logging, and stage-specific prompts.
- **Scholarly retrieval:** Crossref search plus individual DOI metadata lookups. Evidence notes preserve publisher-deposited abstracts and their provenance. Missing evidence, duplicates, known retractions, or insufficient coverage fail the source gate; no fixture fallback occurs in live mode.
- **Authentication:** local accounts, salted scrypt password hashes, expiring/revocable opaque sessions stored as hashes, HttpOnly cookies, CSRF protections, persistent auth throttling, and per-account project/download ownership checks.
- **Web workspace:** responsive English/Persian UI with RTL, private projects, intake, pipeline progress, artifact/source inspection, plan/source/outline approvals, rejection feedback, human retries, cancellation at checkpoints, and downloads.
- **Rendering:** real DOCX and PDF files, Unicode/Persian shaping, headings, registered citations, draft references, AI-use disclosure, and a downloadable JSON evidence audit. Rendering is application code, not a model-supplied file path.
- **Durable core:** SQLite jobs, attempts, versioned artifacts, gate results, usage records, and append-only events; isolated section retries and restart/resume.

This is a **local/small-deployment implementation**, not a fully hardened public SaaS or a guarantee of academic correctness. See [limitations](#limits-and-safety) and [architecture](docs/architecture.md). The roadmap in [milestones](docs/milestones.md) includes additional work beyond this release.

## Install

Python 3.11+ is required. PDF rendering also needs a Unicode TTF font with Persian glyphs; DejaVu Sans is used by default.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check src tests
```

Windows: activate with `.venv\Scripts\activate`. On Debian/Ubuntu, install `fonts-dejavu-core` if `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` is absent. On other systems set `EVIDEX_PDF_FONT` to an installed Unicode `.ttf` font. HarfBuzz text shaping is provided by the Python dependency `uharfbuzz`; no LibreOffice or external PDF service is required.

## Start the web workspace

### Offline, explicitly synthetic demo

```bash
evidex serve --demo --insecure-cookies --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`, create an account (password: 12–128 characters), and create a project. Start the pipeline, inspect the artifacts, and approve **plan → sources → outline**. Completed web projects offer DOCX, PDF, and audit downloads.

**`--insecure-cookies` is for local HTTP only. Omit it behind HTTPS, including hosted previews.** Demo sources are visibly synthetic; generated files must not be submitted or cited as academic evidence.

### Live integrations

Set these variables **in your local shell or deployment secret manager**, not in browser code or Git:

```bash
export EVIDEX_DEMO=0
export EVIDEX_LLM_API_KEY='<your-provider-key>'
export EVIDEX_LLM_MODEL='gpt-4o-mini'
export EVIDEX_CROSSREF_MAILTO='research-admin@example.edu'
# Optional for an OpenAI-compatible service:
# export EVIDEX_LLM_BASE_URL='https://your-provider.example/v1'

evidex serve --host 0.0.0.0 --port 8000
```

Use an HTTPS reverse proxy. For local HTTP testing only, append `--insecure-cookies`. The model must support Chat Completions JSON-object mode and the configured output limit (12,000 tokens). Live mode refuses project creation when no API key is configured; it never silently falls back to the fake provider.

Crossref currently needs no API key; a contact email is recommended. The server needs outbound HTTPS to `api.crossref.org` and the configured LLM host. No credentials are sent to the browser. The live adapter tests use HTTP mocks; tests do not require a network or spend API credits. Live calls still require validation in your provider/network environment.

Copy `.env.example` for reference. **The app reads process environment variables; it does not automatically load `.env` files.** Uvicorn's `--env-file .env` is an alternative:

```bash
uvicorn evidex.api:create_app --factory --env-file .env --host 0.0.0.0 --port 8000
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EVIDEX_DATA_DIR` | `.evidex` | Private DB, lock, and export directory; keep outside public static hosting |
| `EVIDEX_DEMO` | `0` | Explicit fixture mode when `1`; mode is persisted per project |
| `EVIDEX_LLM_API_KEY` | unset | Server-side provider secret, required for live execution |
| `EVIDEX_LLM_MODEL` | `gpt-4o-mini` | JSON-capable model name |
| `EVIDEX_LLM_BASE_URL` | `https://api.openai.com/v1` | Trusted, administrator-configured HTTPS endpoint |
| `EVIDEX_CROSSREF_MAILTO` | unset | Crossref contact email |
| `EVIDEX_PDF_FONT` | `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` | Unicode TTF for embedded PDF text |
| `EVIDEX_SECURE_COOKIES` | `1` | Keep enabled for HTTPS; `0` for local HTTP only |
| `EVIDEX_REGISTRATION` | `1` | Set `0` to disable new accounts after provisioning trusted users |

## Workflow and API

The browser uses only same-origin URLs. No Node build or separate frontend server is needed; assets and versioned prompts are included in the Python wheel. API schemas are available at `/openapi.json`.

Every mutation requires `X-Evidex-Request: 1`. Authentication uses the session cookie; cross-origin CORS access is not enabled.

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/register`, `POST /api/auth/login` | `{ "email": "…", "password": "…" }` |
| `GET /api/auth/me`, `POST /api/auth/logout` | Current session / revoke session |
| `GET /api/config` | Non-secret mode and readiness flags |
| `GET /api/projects`, `POST /api/projects` | List owned projects / create from `ProjectBrief` |
| `GET /api/projects/{id}` | Private status, brief, artifacts, attempts, events, worker state, downloads |
| `POST /api/projects/{id}/actions` | `action`: `run`, `approve`, `reject`, `retry`, or `cancel` |
| `GET /api/projects/{id}/downloads/{format}` | Completed project's `docx`, `pdf`, or `json` export |

Approval/rejection requests must include the checkpoint `stage`. Rejection/retry requests require nonempty `feedback`. Actors are taken from the authenticated account, never a client-supplied identity. Approval changes state; a separate `run` starts work (the UI's “Approve & continue” performs both).

Two in-process threads execute jobs, with at most two more queued. Cross-process filesystem locks prevent simultaneous web actions on the same job. The UI polls while a worker runs. A process restart does not automatically requeue work: click **Start / resume pipeline** to resume from persisted state. A crash between a remote call and persistence may repeat a billable call; provider idempotency is best-effort. Cancellation is supported when no worker owns the job, not during an in-flight provider call.

The CLI is a trusted local operator interface, not an authentication boundary. Do not use it concurrently with web workers on the same jobs.

## Original synthetic CLI

The original deterministic skeleton demo remains available and intentionally does not render files:

```bash
evidex demo --auto-approve --fail-first plan
evidex approve <job-id> plan
evidex run <job-id>
evidex status <job-id>
```

These commands accept `--database PATH`. `run` detects persisted live-mode jobs and requires live provider configuration rather than mixing fixtures into them. CLI-created projects are not attached to a web account. Use the web interface for authenticated workflows and rendered demo downloads.

## Limits and safety

- **Metadata verification is not evidence verification.** Crossref DOI records do not establish claim entailment, full-text access, source relevance, or exhaustive retraction screening. Notes contain the deposited abstract **verbatim**, explicitly labeled as such. Students must inspect the sources. Sources without abstracts cannot supply evidence in this version. Retrieval is bounded to 12 subtopics, 30 search hits per subtopic, and 150 DOI lookups per attempt; coverage may legitimately fail.
- Retrieval retries repeat searches from the approved plan. There is not yet a manual source editor, upload/DOI import flow, full-text retrieval, or additional scholarly-provider fallback. `user_provided_sources` and university-specific templates in the domain schema are not consumed by these integrations.
- Existing deterministic claim/number/citation gates remain intact, but lexical overlap is **not** a semantic entailment or plagiarism judge. Read every generated section. No automatic correctness guarantee is made.
- There is no dataset upload yet. Live original-results/findings sections use code-generated `STUDENT_DATA` placeholders even if intake says `has_data`.
- DOCX/PDF exports are usable drafts, not certified APA/IEEE/Vancouver/CSL formatting. They do not yet implement university templates, automatic TOC, LaTeX, BibTeX/RIS, or exact pagination parity. PDF embeds the configured font; DOCX requests DejaVu Sans and the viewing system may substitute it.
- Live prompts transmit the brief, approved sources, draft sections, and feedback to the configured LLM service; retrieval transmits topic/subtopic searches to Crossref. Assess provider data-retention/privacy terms before using sensitive research.
- Before public multi-user deployment: add verified-email/password-reset/MFA flows, operational monitoring, backup/retention/deletion policy, global token/cost budgets, edge rate/body limits, PostgreSQL, and a durable distributed worker queue. Current limits constrain requests/attempts but do not enforce a dollar budget. Protect the data directory and backups; the local DB/files are not encrypted by this application. Disable open registration for a trusted-user deployment.
- Students remain responsible for institutional AI policies, disclosure, research ethics, and final content. The pipeline never treats synthetic test fixtures as scholarly references in live mode.

See [decisions](docs/decisions.md) for implementation trade-offs.
