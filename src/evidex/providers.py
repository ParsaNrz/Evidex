from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from evidex.gates import GateContext, minimum_source_count
from evidex.models import (
    CitationAuditEntry,
    DataSituation,
    DocumentOutline,
    ExportPackage,
    Language,
    Objective,
    OutlineNode,
    ProjectBrief,
    ResearchPlan,
    ResearchQuestion,
    SearchQuery,
    SectionDraft,
    SourceOrigin,
    SourceRecord,
    SourceRegistry,
    Stage,
    TimelineItem,
    Verification,
    VerificationStatus,
)
from evidex.templates import distribute_words, document_template, section_id


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str


@dataclass(frozen=True)
class LLMRequest:
    job_id: str
    stage: Stage
    task_key: str
    attempt: int
    input_payload: dict[str, Any]
    feedback: str | None
    prompt: Prompt
    idempotency_key: str


@dataclass(frozen=True)
class LLMResponse:
    output: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float | None = None


class LLMProvider(Protocol):
    name: str
    model: str
    fixture_mode: bool

    def complete_json(self, request: LLMRequest) -> LLMResponse: ...


class PromptRegistry:
    PROMPT_FILES: dict[Stage, tuple[str, str]] = {
        Stage.INTAKE: ("intake/normalize.v1.md", "intake.normalize"),
        Stage.PLAN: ("plan/generate.v1.md", "plan.generate"),
        Stage.SOURCES: ("sources/gather.v1.md", "sources.gather"),
        Stage.OUTLINE: ("outline/generate.v1.md", "outline.generate"),
        Stage.WRITE: ("writing/section.v1.md", "writing.section"),
        Stage.REVIEW: ("review/review.v1.md", "review.document"),
        Stage.OUTPUT: ("output/package.v1.md", "output.package"),
    }

    def __init__(self, prompt_dir: str | Path | None = None) -> None:
        self.prompt_dir = (
            Path(prompt_dir) if prompt_dir else Path(__file__).resolve().parents[2] / "prompts"
        )

    def load(self, stage: Stage) -> Prompt:
        relative, name = self.PROMPT_FILES[stage]
        path = self.prompt_dir / relative
        if not path.is_file():
            raise FileNotFoundError(f"Versioned prompt is missing: {path}")
        text = path.read_text(encoding="utf-8")
        version = path.stem.rsplit(".v", maxsplit=1)[-1]
        return Prompt(name=name, version=version, text=text)


class FakeLLM:
    """Deterministic, clearly synthetic provider for local tests and demonstrations only."""

    name = "fake"
    model = "evidex-fake-v1"
    fixture_mode = True

    def __init__(
        self,
        fail_first_stages: set[str] | None = None,
        fail_first_tasks: set[str] | None = None,
    ) -> None:
        self.fail_first_stages = fail_first_stages or set()
        self.fail_first_tasks = fail_first_tasks or set()
        self.calls: list[LLMRequest] = []

    def complete_json(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        started = time.perf_counter()
        output = self._make_output(request)
        forced_failure = (
            request.stage.value in self.fail_first_stages
            or request.task_key in self.fail_first_tasks
        ) and request.attempt == 1
        if forced_failure:
            output = self._inject_gate_failure(request.stage, output)
        elapsed = int((time.perf_counter() - started) * 1000)
        serialized_input = json.dumps(
            {
                "prompt": request.prompt.text,
                "input": request.input_payload,
                "feedback": request.feedback,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        serialized_output = json.dumps(output, ensure_ascii=False, sort_keys=True)
        return LLMResponse(
            output=output,
            provider=self.name,
            model=self.model,
            input_tokens=max(1, len(serialized_input) // 4),
            output_tokens=max(1, len(serialized_output) // 4),
            latency_ms=elapsed,
            cost_usd=0.0,
        )

    def _make_output(self, request: LLMRequest) -> dict[str, Any]:
        if request.stage == Stage.INTAKE:
            return ProjectBrief.model_validate(request.input_payload["brief"]).model_dump(
                mode="json"
            )
        if request.stage == Stage.PLAN:
            return self._plan(request.input_payload)
        if request.stage == Stage.SOURCES:
            return self._sources(request.input_payload)
        if request.stage == Stage.OUTLINE:
            return self._outline(request.input_payload)
        if request.stage == Stage.WRITE:
            return self._section(request.input_payload)
        if request.stage == Stage.REVIEW:
            return self._review(request.input_payload)
        if request.stage == Stage.OUTPUT:
            return self._output(request.input_payload)
        raise ValueError(f"Fake provider does not implement {request.stage.value}")

    @staticmethod
    def _brief(payload: dict[str, Any]) -> ProjectBrief:
        return ProjectBrief.model_validate(payload["brief"])

    def _plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = self._brief(payload)
        subtopics = [
            f"concepts and definitions in {brief.field}",
            f"research methods for {brief.topic}",
            f"evidence and limitations concerning {brief.topic}",
        ]
        questions = [
            ResearchQuestion(
                question_id="rq-1", text=f"How is {brief.topic} defined in the selected field?"
            ),
            ResearchQuestion(
                question_id="rq-2",
                text=f"Which methods are appropriate for examining {brief.topic}?",
            ),
            ResearchQuestion(
                question_id="rq-3",
                text=f"What evidence and limitations shape understanding of {brief.topic}?",
            ),
        ]
        objectives = [
            Objective(
                objective_id="obj-1",
                text="Synthesize the key concepts and relevant evidence.",
                question_ids=["rq-1", "rq-3"],
            ),
            Objective(
                objective_id="obj-2",
                text="Specify a feasible method and its limitations.",
                question_ids=["rq-2", "rq-3"],
            ),
        ]
        budgets = distribute_words(brief)
        queries = [SearchQuery(query=brief.topic, language=Language.ENGLISH)]
        keywords_fa = [brief.topic] if brief.language == Language.PERSIAN else []
        if brief.language == Language.PERSIAN:
            queries.append(SearchQuery(query=f"{brief.topic} پژوهش", language=Language.PERSIAN))
        keywords_en = [brief.topic, brief.field]
        plan = ResearchPlan(
            problem_statement=f"The project examines the bounded research problem of {brief.topic} in {brief.field}.",
            research_questions=questions,
            objectives=objectives,
            scope=f"The study is limited to {brief.topic} in the context of {brief.field}.",
            limitations=[
                "The scope and conclusions depend on the sources and data approved by the student."
            ],
            methodology_type=brief.methodology,
            keywords_fa=keywords_fa,
            keywords_en=keywords_en,
            search_queries=queries,
            subtopics=subtopics,
            section_budgets=budgets,
            timeline=[
                TimelineItem(milestone="Source review and plan refinement", duration_weeks=3),
                TimelineItem(milestone="Student data work and drafting", duration_weeks=6),
                TimelineItem(milestone="Revision and formatting", duration_weeks=2),
            ],
        )
        return plan.model_dump(mode="json")

    def _sources(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = self._brief(payload)
        plan = ResearchPlan.model_validate(payload["plan"])
        required = minimum_source_count(GateContext(brief=brief))
        current_year = date.today().year
        subtopics = plan.subtopics
        sources: list[SourceRecord] = []
        coverage: dict[str, list[str]] = {subtopic: [] for subtopic in subtopics}
        for index in range(1, required + 1):
            source_id = f"fixture-{index:03d}"
            subtopic = subtopics[(index - 1) % len(subtopics)]
            note_id = f"note-{index:03d}"
            if brief.language == Language.PERSIAN:
                paraphrase = f"یادداشت شاهد نمونه درباره {subtopic} که فقط برای آزمون مسیر شواهد ساخته شده است"
                title = f"نمونه ساختگی {index} درباره {subtopic}"
                language = Language.PERSIAN
            else:
                paraphrase = f"Synthetic fixture evidence about {subtopic}, created only to test evidence tracing"
                title = f"Synthetic fixture {index} about {subtopic}"
                language = Language.ENGLISH
            source = SourceRecord(
                source_id=source_id,
                source_type="test_fixture",
                title=title,
                authors=[f"Fixture Author {index}"],
                year=current_year - 4 + index % 5,
                venue="Synthetic test fixture",
                language=language,
                abstract=paraphrase,
                origin=SourceOrigin.TEST_FIXTURE,
                verification=Verification(status=VerificationStatus.FIXTURE, method="test_fixture"),
                relevance_score=0.9,
                notes=[
                    {
                        "note_id": note_id,
                        "paraphrase": paraphrase,
                        "locator": "fixture only; no external source or page exists",
                    }
                ],
            )
            sources.append(source)
            coverage[subtopic].append(source_id)
        return SourceRegistry(sources=sources, subtopic_sources=coverage).model_dump(mode="json")

    def _outline(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = self._brief(payload)
        plan = ResearchPlan.model_validate(payload["plan"])
        registry = SourceRegistry.model_validate(payload["registry"])
        budgets = distribute_words(brief)
        content_nodes = [
            section.title for section in document_template(brief) if section.substantive
        ]
        source_assignments: dict[str, list[str]] = {title: [] for title in content_nodes}
        for index, source in enumerate(registry.sources):
            source_assignments[content_nodes[index % len(content_nodes)]].append(source.source_id)
        nodes: list[OutlineNode] = []
        for section in document_template(brief):
            nodes.append(
                OutlineNode(
                    node_id=section_id(section.title),
                    title=section.title,
                    purpose=f"Address the approved scope of {brief.topic} in this document section.",
                    key_points=[
                        "Use only approved evidence and identify uncertainty.",
                        "Do not invent results, numbers, or source details.",
                    ],
                    objective_ids=[objective.objective_id for objective in plan.objectives],
                    question_ids=[question.question_id for question in plan.research_questions],
                    source_ids=source_assignments.get(section.title, []),
                    word_budget=budgets.get(section.title, 0),
                )
            )
        return DocumentOutline(nodes=nodes).model_dump(mode="json")

    def _section(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = self._brief(payload)
        node = OutlineNode.model_validate(payload["node"])
        registry = SourceRegistry.model_validate(payload["registry"])
        if "results" in node.title.casefold() or "findings" in node.title.casefold():
            if brief.data_situation != DataSituation.HAS_DATA:
                if brief.language == Language.PERSIAN:
                    body = "[STUDENT_DATA: داده‌ها و تحلیل خود را برای نگارش یافته‌ها اضافه کنید.]"
                else:
                    body = "[STUDENT_DATA: Add your dataset and analysis before drafting findings.]"
                return SectionDraft(
                    section_id=node.node_id,
                    title=node.title,
                    language=brief.language,
                    body=body,
                    claims=[],
                ).model_dump(mode="json")
        source_map = {source.source_id: source for source in registry.sources}
        source_id = node.source_ids[0] if node.source_ids else registry.sources[0].source_id
        source = source_map[source_id]
        note = source.notes[0]
        claim_text = note.paraphrase
        if brief.language == Language.PERSIAN:
            filler = "این بخش در چارچوب مسئله، هدف‌ها و روش مصوب توضیح داده می‌شود"
        else:
            filler = "This section stays within the approved scope, objectives, and method"
        text_parts = [claim_text]
        while len(" ".join(text_parts).split()) < max(1, int(node.word_budget * 0.92)):
            text_parts.append(filler)
        body = " ".join(text_parts) + f" [@{source_id}]"
        return SectionDraft(
            section_id=node.node_id,
            title=node.title,
            language=brief.language,
            body=body,
            claims=[
                {
                    "claim_id": f"claim-{node.node_id}-1",
                    "text": claim_text,
                    "source_ids": [source_id],
                    "evidence_note_ids": [note.note_id],
                }
            ],
        ).model_dump(mode="json")

    def _review(self, payload: dict[str, Any]) -> dict[str, Any]:
        sections = [SectionDraft.model_validate(section) for section in payload["sections"]]
        source_ids = sorted(
            {
                source_id
                for section in sections
                for claim in section.claims
                for source_id in claim.source_ids
            }
        )
        return {
            "summary": "Fixture review completed; this report is synthetic and not a scholarly review.",
            "issues": [],
            "cited_source_ids": source_ids,
            "reference_source_ids": source_ids,
            "confidence_notes": ["Fixture-only review; no semantic entailment judge was run."],
        }

    def _output(self, payload: dict[str, Any]) -> dict[str, Any]:
        sections = [SectionDraft.model_validate(section) for section in payload["sections"]]
        registry = SourceRegistry.model_validate(payload["registry"])
        source_map = {source.source_id: source for source in registry.sources}
        claims_by_source: dict[str, list[str]] = {}
        notes_by_source: dict[str, list[str]] = {}
        for section in sections:
            for claim in section.claims:
                for source_id in claim.source_ids:
                    claims_by_source.setdefault(source_id, []).append(claim.claim_id)
                    notes_by_source.setdefault(source_id, []).extend(claim.evidence_note_ids)
        audit = [
            CitationAuditEntry(
                source_id=source_id,
                verification_status=source_map[source_id].verification.status,
                claim_ids=claim_ids,
                evidence_note_ids=notes_by_source[source_id],
            )
            for source_id, claim_ids in sorted(claims_by_source.items())
        ]
        return ExportPackage(
            files=[],
            citation_audit=audit,
            change_log=["Synthetic pipeline demonstration; no real document was rendered."],
            human_overrides=payload.get("overrides", []),
            ai_use_disclosure=None,
            audit_complete=True,
            demo_mode=True,
        ).model_dump(mode="json")

    @staticmethod
    def _inject_gate_failure(stage: Stage, output: dict[str, Any]) -> dict[str, Any]:
        if stage == Stage.PLAN and output.get("objectives"):
            output["objectives"][0]["question_ids"] = []
        elif stage == Stage.OUTLINE and output.get("nodes"):
            output["nodes"][0]["word_budget"] += 1000
        elif stage == Stage.WRITE:
            output["body"] = output["body"].replace("[@", "[@unregistered-")
        elif stage == Stage.REVIEW:
            output["issues"] = [
                {
                    "issue_id": "fixture-forced-review-failure",
                    "severity": "error",
                    "description": "Forced fixture review failure for retry testing.",
                    "target_sections": ["problem-statement"],
                }
            ]
        return output
