# Evidex

Evidex is a Persian-first academic-writing workspace in development. It is designed around a strict, auditable pipeline: application code controls stage order and retries; every model result must validate against a schema and pass a gate; students approve the plan, sources, and outline. The system must not invent citations, data, findings, interview quotes, or survey responses.

## Current status

**Milestone 1 (pipeline skeleton) is implemented.** This repository currently contains the durable workflow core and a deterministic synthetic provider used for tests and local demonstrations. It does **not** yet contain real LLM or scholarly retrieval integrations, authentication, a web UI, or DOCX/PDF rendering. Demo source records are visibly marked as fixtures, are accepted only in fixture mode, and must never be represented as real references.

See [the architecture](docs/architecture.md), [milestone plan](docs/milestones.md), and [decision log](docs/decisions.md).

## Requirements

- Python 3.11 or newer (compatible with Python 3.12)
- No external database, Redis, model key, or scholarly API credentials required for the skeleton

## Install and test

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

On Windows, activate with `.venv\\Scripts\\activate`.

## Run the synthetic pipeline

Run an explicitly labelled, synthetic proposal through all seven stages, simulating student approvals and forcing a plan-gate failure so the feedback-and-retry path is visible:

```bash
evidex demo --auto-approve --fail-first plan
```

The demo uses a local SQLite database at `.evidex/evidex.sqlite3` (ignored by Git). It is not a real academic draft, does not use real sources, and produces no downloadable files. Without `--auto-approve`, the command stops at the plan approval checkpoint. The `approve` and `run` commands resume a persisted job:

```bash
evidex approve <job-id> plan
evidex run <job-id>
evidex approve <job-id> sources
evidex run <job-id>
evidex approve <job-id> outline
evidex run <job-id>
evidex status <job-id>
```

All commands accept `--database PATH` if a different SQLite file is preferred. Use `evidex demo --help` for the fixture's document type, degree, language, and topic options.

## Implemented in Milestone 1

- Pydantic v2 domain schemas for intake, plans, source registries, outlines, claims/sections, reviews, outputs, gates, and model-call metadata.
- A closed, explicit state machine with code-owned stage order, per-stage retries, approval checkpoints, review routing, cancellation, human retry, and logged failed-check overrides.
- SQLite persistence for job state, attempt inputs/outputs, versioned artifacts, gate results, model-call metadata, and append-only events.
- Versioned prompt files and a provider interface, with a deterministic fake provider for offline end-to-end runs.
- Deterministic gates for request consistency, objective/question mapping, source counts/coverage/retractions, outline completeness/budgets, citation/evidence links, number tracing, review references, and audit packaging.
- Tests for every current gate, invalid transitions, forced gate and per-section retries with feedback, human checkpoints, retry exhaustion, review routing, override logging, and SQLite restart/resume.

## Safety note

The synthetic provider intentionally generates fixture content and registry entries for software tests only. It is not evidence, and the demo output must not be submitted or cited as academic work. Future production execution must require real source verification, student approval, and an explicit AI-use disclosure where required by the institution. Students remain responsible for following their university's AI-assistance policy.
