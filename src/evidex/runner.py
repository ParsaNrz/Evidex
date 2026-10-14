from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from evidex.gates import GateContext, evaluate_gate, schema_failure
from evidex.models import (
    DocumentOutline,
    ExportPackage,
    GateResult,
    JobState,
    JobStatus,
    ModelCallRecord,
    ProjectBrief,
    ResearchPlan,
    ReviewReport,
    SectionDraft,
    SourceRegistry,
    Stage,
    utc_now,
)
from evidex.providers import FakeLLM, LLMProvider, LLMRequest, PromptRegistry
from evidex.state_machine import (
    APPROVAL_STAGES,
    NEXT_STAGE,
    InvalidTransition,
    assert_stage_transition,
)
from evidex.store import SQLiteStore

logger = logging.getLogger("evidex.pipeline")
T = TypeVar("T", bound=BaseModel)


@dataclass
class PipelineConfig:
    max_attempts: dict[Stage, int] = field(
        default_factory=lambda: {
            Stage.INTAKE: 3,
            Stage.PLAN: 3,
            Stage.SOURCES: 4,
            Stage.OUTLINE: 3,
            Stage.WRITE: 3,
            Stage.REVIEW: 3,
            Stage.OUTPUT: 2,
        }
    )
    max_review_cycles: int = 3
    max_steps_per_run: int = 500


class PipelineRunner:
    """Explicit, resumable state machine. The provider never selects a next stage."""

    SCHEMAS: dict[Stage, type[BaseModel]] = {
        Stage.INTAKE: ProjectBrief,
        Stage.PLAN: ResearchPlan,
        Stage.SOURCES: SourceRegistry,
        Stage.OUTLINE: DocumentOutline,
        Stage.WRITE: SectionDraft,
        Stage.REVIEW: ReviewReport,
        Stage.OUTPUT: ExportPackage,
    }

    def __init__(
        self,
        store: SQLiteStore,
        provider: LLMProvider | None = None,
        prompt_registry: PromptRegistry | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.store = store
        self.provider = provider or FakeLLM()
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.config = config or PipelineConfig()

    def create_project(self, brief: ProjectBrief, job_id: str | None = None) -> JobState:
        return self.store.create_job(brief, job_id or str(uuid.uuid4()), data={
            "execution_mode": "demo" if self.provider.fixture_mode else "live"
        })

    def run(self, job_id: str, *, max_steps: int | None = None) -> JobState:
        state = self.store.get_job(job_id)
        mode = "demo" if self.provider.fixture_mode else "live"
        if state.data.get("execution_mode", "demo") != mode:
            raise ValueError("Execution mode mismatch: refusing to mix real sources and fixtures")
        if state.status in {
            JobStatus.AWAITING_APPROVAL,
            JobStatus.NEEDS_HUMAN,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
            JobStatus.FAILED,
        }:
            return state
        if state.status == JobStatus.PENDING:
            state = self.store.transition_job(
                job_id,
                "pipeline_started",
                {"message": "Pipeline execution started by application code."},
                status=JobStatus.RUNNING,
                current_stage=Stage.INTAKE,
                attempt=1,
                task_key="intake",
                feedback_for_retry=None,
            )
        limit = max_steps or self.config.max_steps_per_run
        steps = 0
        while steps < limit:
            steps += 1
            state = self.store.get_job(job_id)
            if state.status in {
                JobStatus.AWAITING_APPROVAL,
                JobStatus.NEEDS_HUMAN,
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
                JobStatus.FAILED,
            }:
                return state
            if state.status == JobStatus.GATE_PASSED:
                state = self._advance_after_pass(state)
                continue
            if state.status == JobStatus.GATE_FAILED:
                state = self._handle_gate_failure(state)
                continue
            if state.status != JobStatus.RUNNING or state.current_stage is None:
                return state
            state = self._prepare_current_task(state)
            if state.status != JobStatus.RUNNING:
                continue
            stage = state.current_stage
            task_key = state.task_key or stage.value
            prior_gate = self.store.get_gate_result(job_id, stage, task_key, state.attempt)
            if prior_gate:
                state = self._apply_gate_result(state, prior_gate)
                continue
            self._execute_attempt(state)
        logger.warning("Pipeline stopped after step safety limit", extra={"job_id": job_id})
        return self.store.get_job(job_id)

    def approve(self, job_id: str, stage: Stage, *, actor: str = "student") -> JobState:
        state = self.store.get_job(job_id)
        if state.status != JobStatus.AWAITING_APPROVAL or state.pending_approval != stage:
            raise InvalidTransition(f"Job is not awaiting approval for {stage.value}")
        next_stage = NEXT_STAGE[stage]
        if next_stage is None:
            raise InvalidTransition("No approval checkpoint exists after the output stage")
        data = dict(state.data)
        changes: dict[str, Any] = {
            "status": JobStatus.RUNNING,
            "current_stage": next_stage,
            "attempt": 1,
            "task_key": next_stage.value,
            "feedback_for_retry": None,
            "pending_approval": None,
            "data": data,
        }
        if next_stage == Stage.WRITE:
            outline = self._load_artifact(job_id, Stage.OUTLINE, "outline", DocumentOutline)
            queue = [node.node_id for node in outline.nodes if node.word_budget > 0]
            if not queue:
                raise InvalidTransition("Approved outline has no writable sections")
            changes.update(
                {
                    "section_queue": queue,
                    "section_cursor": 0,
                    "task_key": queue[0],
                    "attempt": 1,
                    "review_cycle": 0,
                }
            )
        state = self.store.transition_job(
            job_id,
            "approval_accepted",
            {"approved_stage": stage.value, "actor": actor},
            **changes,
        )
        return state

    def reject_approval(
        self, job_id: str, stage: Stage, feedback: str, *, actor: str = "student"
    ) -> JobState:
        state = self.store.get_job(job_id)
        if state.status != JobStatus.AWAITING_APPROVAL or state.pending_approval != stage:
            raise InvalidTransition(f"Job is not awaiting approval for {stage.value}")
        return self.store.transition_job(
            job_id,
            "approval_rejected",
            {"rejected_stage": stage.value, "actor": actor, "feedback": feedback},
            status=JobStatus.NEEDS_HUMAN,
            pending_approval=None,
            feedback_for_retry=feedback,
        )

    def request_retry(self, job_id: str, feedback: str, *, actor: str = "student") -> JobState:
        state = self.store.get_job(job_id)
        if state.status != JobStatus.NEEDS_HUMAN or state.current_stage is None:
            raise InvalidTransition("Only a job paused for human intervention can be retried")
        return self.store.transition_job(
            job_id,
            "human_retry_requested",
            {"actor": actor, "feedback": feedback, "previous_attempt": state.attempt},
            status=JobStatus.RUNNING,
            attempt=state.attempt + 1,
            feedback_for_retry=feedback,
        )

    def override_failed_checks(
        self,
        job_id: str,
        check_ids: list[str],
        note: str,
        *,
        actor: str = "student",
    ) -> JobState:
        state = self.store.get_job(job_id)
        if (
            state.status != JobStatus.NEEDS_HUMAN
            or state.current_stage is None
            or not state.task_key
        ):
            raise InvalidTransition("A failed gate must be paused for a human before override")
        gate = self.store.get_gate_result(
            job_id, state.current_stage, state.task_key, state.attempt
        )
        if gate is None:
            raise InvalidTransition("No persisted gate result exists for the paused attempt")
        failed_ids = {check.check_id for check in gate.checks if not check.passed}
        if not check_ids or not set(check_ids).issubset(failed_ids):
            raise ValueError(
                "Overrides must name one or more failed check IDs from the latest gate"
            )
        if not note.strip():
            raise ValueError("An override requires an audit note")
        overrides = list(state.data.get("overrides", []))
        overrides.append(
            {
                "stage": state.current_stage.value,
                "task_key": state.task_key,
                "attempt": state.attempt,
                "check_ids": check_ids,
                "note": note,
                "actor": actor,
                "created_at": utc_now().isoformat(),
            }
        )
        state = self.store.transition_job(
            job_id,
            "gate_overridden",
            {
                "stage": state.current_stage.value,
                "check_ids": check_ids,
                "note": note,
                "actor": actor,
            },
            status=JobStatus.GATE_PASSED,
            data={**state.data, "overrides": overrides},
        )
        return self._advance_after_pass(state)

    def cancel(self, job_id: str, *, actor: str = "student") -> JobState:
        state = self.store.get_job(job_id)
        if state.status in {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED}:
            return state
        return self.store.transition_job(
            job_id,
            "job_cancelled",
            {"actor": actor},
            status=JobStatus.CANCELLED,
            pending_approval=None,
        )

    def _prepare_current_task(self, state: JobState) -> JobState:
        if state.current_stage != Stage.WRITE:
            return state
        if not state.section_queue:
            outline = self._load_artifact(state.job_id, Stage.OUTLINE, "outline", DocumentOutline)
            queue = [node.node_id for node in outline.nodes if node.word_budget > 0]
            if not queue:
                return self.store.transition_job(
                    state.job_id,
                    "outline_has_no_writable_sections",
                    {"reason": "No outline node has a positive word budget."},
                    status=JobStatus.NEEDS_HUMAN,
                )
            return self.store.transition_job(
                state.job_id,
                "writing_queue_created",
                {"section_ids": queue},
                section_queue=queue,
                section_cursor=0,
                task_key=self._write_task_key(queue[0], state.review_cycle),
                attempt=1,
            )
        if state.section_cursor >= len(state.section_queue):
            return self._move_to_review(state)
        node_id = state.section_queue[state.section_cursor]
        expected_task = self._write_task_key(node_id, state.review_cycle)
        if state.task_key != expected_task:
            return self.store.transition_job(
                state.job_id,
                "writing_section_selected",
                {"section_id": node_id, "review_cycle": state.review_cycle},
                task_key=expected_task,
                attempt=1,
                feedback_for_retry=None,
            )
        return state

    @staticmethod
    def _write_task_key(node_id: str, review_cycle: int) -> str:
        return node_id if review_cycle == 0 else f"{node_id}#review-{review_cycle}"

    def _execute_attempt(self, state: JobState) -> None:
        assert state.current_stage is not None
        stage = state.current_stage
        task_key = state.task_key or stage.value
        attempt = state.attempt
        input_payload, section_node = self._build_input(state)
        prompt = self.prompt_registry.load(stage)
        attempt_input = {
            "input": input_payload,
            "retry_feedback": state.feedback_for_retry,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_sha256": hashlib.sha256(prompt.text.encode("utf-8")).hexdigest(),
        }
        self.store.start_attempt(state.job_id, stage, task_key, attempt, attempt_input)
        persisted_attempt = self.store.get_attempt(state.job_id, stage, task_key, attempt)
        if persisted_attempt and persisted_attempt["output"] is not None:
            raw_output = persisted_attempt["output"]
        else:
            idempotency_key = f"{state.job_id}:{stage.value}:{task_key}:{attempt}"
            request = LLMRequest(
                job_id=state.job_id,
                stage=stage,
                task_key=task_key,
                attempt=attempt,
                input_payload=input_payload,
                feedback=state.feedback_for_retry,
                prompt=prompt,
                idempotency_key=idempotency_key,
            )
            input_hash = hashlib.sha256(
                json.dumps(attempt_input, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            started = time.perf_counter()
            try:
                response = self.provider.complete_json(request)
                latency = max(response.latency_ms, int((time.perf_counter() - started) * 1000))
                call_record = ModelCallRecord(
                    call_id=str(uuid.uuid4()),
                    job_id=state.job_id,
                    stage=stage,
                    task_key=task_key,
                    attempt=attempt,
                    provider=response.provider,
                    model=response.model,
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    status="response_received",
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_usd=response.cost_usd,
                    latency_ms=latency,
                )
                raw_output = response.output
                self.store.save_model_call(call_record)
                self.store.finish_attempt(
                    state.job_id,
                    stage,
                    task_key,
                    attempt,
                    status="output_ready",
                    output=raw_output,
                )
            except (
                Exception
            ) as exc:  # Provider failures are persisted and retried via the ordinary gate path.
                latency = int((time.perf_counter() - started) * 1000)
                call_record = ModelCallRecord(
                    call_id=str(uuid.uuid4()),
                    job_id=state.job_id,
                    stage=stage,
                    task_key=task_key,
                    attempt=attempt,
                    provider=getattr(self.provider, "name", type(self.provider).__name__),
                    model=getattr(self.provider, "model", "unknown"),
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    status="provider_error",
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_ms=max(0, latency),
                    error=str(exc),
                )
                self.store.save_model_call(call_record)
                raw_output = {}
                self.store.finish_attempt(
                    state.job_id,
                    stage,
                    task_key,
                    attempt,
                    status="provider_error",
                    output=raw_output,
                    error=str(exc),
                )
        self.store.save_artifact(state.job_id, stage, task_key, attempt, raw_output)
        schema = self.SCHEMAS[stage]
        try:
            output = schema.model_validate(raw_output)
        except ValidationError as exc:
            gate = schema_failure(stage, str(exc))
            self.store.finish_attempt(
                state.job_id,
                stage,
                task_key,
                attempt,
                status="schema_failed",
                output=raw_output,
                error=str(exc),
            )
        else:
            context = self._gate_context(state.job_id)
            if stage == Stage.WRITE:
                if section_node is None:
                    raise RuntimeError("Missing outline node for section writer")
                sections = self._sections_for_job(state.job_id)
                gate = evaluate_gate(stage, output, context, section_node=section_node)
            elif stage in {Stage.REVIEW, Stage.OUTPUT}:
                sections = self._sections_for_job(state.job_id)
                gate = evaluate_gate(stage, output, context, sections=sections)
            else:
                gate = evaluate_gate(stage, output, context)
            self.store.finish_attempt(
                state.job_id,
                stage,
                task_key,
                attempt,
                status="passed" if gate.passed else "gate_failed",
                output=raw_output,
                error=None if gate.passed else gate.feedback_for_retry,
            )
        self.store.save_gate_result(state.job_id, stage, task_key, attempt, gate)
        current = self.store.get_job(state.job_id)
        self._apply_gate_result(current, gate)

    def _apply_gate_result(self, state: JobState, gate: GateResult) -> JobState:
        if state.status != JobStatus.RUNNING:
            return state
        if gate.passed:
            state = self.store.transition_job(
                state.job_id,
                "gate_passed",
                {
                    "gate_id": gate.gate_id,
                    "stage": gate.stage.value,
                    "attempt": state.attempt,
                    "checks": [check.model_dump(mode="json") for check in gate.checks],
                },
                status=JobStatus.GATE_PASSED,
                feedback_for_retry=None,
            )
            return self._advance_after_pass(state)
        state = self.store.transition_job(
            state.job_id,
            "gate_failed",
            {
                "gate_id": gate.gate_id,
                "stage": gate.stage.value,
                "attempt": state.attempt,
                "checks": [check.model_dump(mode="json") for check in gate.checks],
                "feedback_for_retry": gate.feedback_for_retry,
                "route_to": [target.model_dump(mode="json") for target in (gate.route_to or [])],
            },
            status=JobStatus.GATE_FAILED,
        )
        return self._handle_gate_failure(state)

    def _handle_gate_failure(self, state: JobState) -> JobState:
        if state.current_stage is None or state.task_key is None:
            return self.store.transition_job(
                state.job_id,
                "pipeline_failed_missing_stage",
                {},
                status=JobStatus.FAILED,
            )
        gate = self.store.get_gate_result(
            state.job_id, state.current_stage, state.task_key, state.attempt
        )
        if gate is None:
            return self.store.transition_job(
                state.job_id,
                "pipeline_failed_missing_gate",
                {"reason": "A failed status had no persisted gate result."},
                status=JobStatus.NEEDS_HUMAN,
            )
        feedback = gate.feedback_for_retry or "Review the failed checks and correct this stage."
        if state.current_stage == Stage.REVIEW:
            next_cycle = state.review_cycle + 1
            routes = [target.section_id for target in gate.route_to or []]
            if routes and next_cycle < self.config.max_review_cycles:
                return self.store.transition_job(
                    state.job_id,
                    "review_routed_to_sections",
                    {
                        "review_cycle": next_cycle,
                        "section_ids": routes,
                        "feedback": feedback,
                    },
                    status=JobStatus.RUNNING,
                    current_stage=Stage.WRITE,
                    task_key=self._write_task_key(routes[0], next_cycle),
                    attempt=1,
                    feedback_for_retry=feedback,
                    pending_approval=None,
                    section_queue=routes,
                    section_cursor=0,
                    review_cycle=next_cycle,
                    review_routed=True,
                )
            if not routes and state.attempt < self.config.max_review_cycles:
                return self.store.transition_job(
                    state.job_id,
                    "review_retry_requested",
                    {"attempt": state.attempt + 1, "feedback": feedback},
                    status=JobStatus.RUNNING,
                    attempt=state.attempt + 1,
                    task_key="review",
                    feedback_for_retry=feedback,
                    review_cycle=next_cycle,
                )
            return self.store.transition_job(
                state.job_id,
                "review_cycles_exhausted",
                {
                    "review_cycle": state.review_cycle,
                    "attempt": state.attempt,
                    "feedback": feedback,
                },
                status=JobStatus.NEEDS_HUMAN,
                feedback_for_retry=feedback,
            )
        max_attempts = self.config.max_attempts.get(state.current_stage, 1)
        if state.attempt < max_attempts:
            return self.store.transition_job(
                state.job_id,
                "stage_retry_scheduled",
                {
                    "stage": state.current_stage.value,
                    "task_key": state.task_key,
                    "next_attempt": state.attempt + 1,
                    "feedback": feedback,
                },
                status=JobStatus.RUNNING,
                attempt=state.attempt + 1,
                feedback_for_retry=feedback,
            )
        return self.store.transition_job(
            state.job_id,
            "stage_attempts_exhausted",
            {
                "stage": state.current_stage.value,
                "task_key": state.task_key,
                "attempt": state.attempt,
                "max_attempts": max_attempts,
                "feedback": feedback,
            },
            status=JobStatus.NEEDS_HUMAN,
            feedback_for_retry=feedback,
        )

    def _advance_after_pass(self, state: JobState) -> JobState:
        stage = state.current_stage
        if stage is None:
            return state
        if stage in APPROVAL_STAGES:
            return self.store.transition_job(
                state.job_id,
                "awaiting_human_approval",
                {"approval_stage": stage.value},
                status=JobStatus.AWAITING_APPROVAL,
                pending_approval=stage,
            )
        if stage == Stage.WRITE:
            completed = dict(state.data.get("completed_sections", {}))
            if state.task_key is None:
                raise RuntimeError("Writing task has no task key")
            completed[state.section_queue[state.section_cursor]] = {
                "task_key": state.task_key,
                "attempt": state.attempt,
            }
            data = {**state.data, "completed_sections": completed}
            next_cursor = state.section_cursor + 1
            if next_cursor < len(state.section_queue):
                node_id = state.section_queue[next_cursor]
                return self.store.transition_job(
                    state.job_id,
                    "section_gate_passed",
                    {"section_id": node_id, "completed_count": len(completed)},
                    status=JobStatus.RUNNING,
                    task_key=self._write_task_key(node_id, state.review_cycle),
                    attempt=1,
                    feedback_for_retry=None,
                    section_cursor=next_cursor,
                    data=data,
                )
            state = self.store.transition_job(
                state.job_id,
                "all_queued_sections_passed",
                {"completed_sections": sorted(completed)},
                status=JobStatus.RUNNING,
                current_stage=Stage.REVIEW,
                task_key="review",
                attempt=max(1, state.review_cycle + 1),
                feedback_for_retry=None,
                section_queue=[],
                section_cursor=0,
                data=data,
            )
            return state
        next_stage = NEXT_STAGE[stage]
        if next_stage is None:
            return self.store.transition_job(
                state.job_id,
                "pipeline_completed",
                {"output_artifact": True},
                status=JobStatus.COMPLETED,
                current_stage=None,
                task_key=None,
                attempt=0,
                pending_approval=None,
                feedback_for_retry=None,
            )
        return self.store.transition_job(
            state.job_id,
            "stage_advanced",
            {"completed_stage": stage.value, "next_stage": next_stage.value},
            status=JobStatus.RUNNING,
            current_stage=next_stage,
            task_key=next_stage.value,
            attempt=1,
            feedback_for_retry=None,
            pending_approval=None,
        )

    def _move_to_review(self, state: JobState) -> JobState:
        assert_stage_transition(state.current_stage, Stage.REVIEW, review_routed=False)
        return self.store.transition_job(
            state.job_id,
            "writing_queue_completed",
            {"completed_sections": state.section_queue},
            status=JobStatus.RUNNING,
            current_stage=Stage.REVIEW,
            task_key="review",
            attempt=max(1, state.review_cycle + 1),
            feedback_for_retry=None,
            section_queue=[],
            section_cursor=0,
        )

    def _build_input(self, state: JobState) -> tuple[dict[str, Any], Any | None]:
        job_id = state.job_id
        brief = self._brief_for_job(job_id)
        stage = state.current_stage
        assert stage is not None
        if stage == Stage.INTAKE:
            return {"brief": self.store.get_input(job_id).model_dump(mode="json")}, None
        if stage == Stage.PLAN:
            return {"brief": brief.model_dump(mode="json")}, None
        plan = self._load_artifact(job_id, Stage.PLAN, "plan", ResearchPlan)
        if stage == Stage.SOURCES:
            return {
                "brief": brief.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
            }, None
        registry = self._load_artifact(job_id, Stage.SOURCES, "sources", SourceRegistry)
        if stage == Stage.OUTLINE:
            return {
                "brief": brief.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "registry": registry.model_dump(mode="json"),
            }, None
        outline = self._load_artifact(job_id, Stage.OUTLINE, "outline", DocumentOutline)
        if stage == Stage.WRITE:
            section_id_value = state.section_queue[state.section_cursor]
            node = next(node for node in outline.nodes if node.node_id == section_id_value)
            earlier = self._sections_for_job(job_id)
            summary = [
                {"section_id": item.section_id, "title": item.title, "summary": item.body[:240]}
                for item in earlier
                if item.section_id != node.node_id
            ]
            return {
                "brief": brief.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "registry": registry.model_dump(mode="json"),
                "node": node.model_dump(mode="json"),
                "earlier_section_summaries": summary,
            }, node
        sections = [section.model_dump(mode="json") for section in self._sections_for_job(job_id)]
        if stage == Stage.REVIEW:
            return {
                "brief": brief.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "registry": registry.model_dump(mode="json"),
                "outline": outline.model_dump(mode="json"),
                "sections": sections,
            }, None
        if stage == Stage.OUTPUT:
            review = self._load_artifact(job_id, Stage.REVIEW, "review", ReviewReport)
            return {
                "brief": brief.model_dump(mode="json"),
                "registry": registry.model_dump(mode="json"),
                "outline": outline.model_dump(mode="json"),
                "sections": sections,
                "review": review.model_dump(mode="json"),
                "overrides": state.data.get("overrides", []),
            }, None
        raise ValueError(f"Unhandled pipeline stage {stage.value}")

    def _brief_for_job(self, job_id: str) -> ProjectBrief:
        raw = self.store.get_artifact(job_id, Stage.INTAKE, "intake")
        return ProjectBrief.model_validate(raw) if raw else self.store.get_input(job_id)

    def _gate_context(self, job_id: str) -> GateContext:
        brief = self._brief_for_job(job_id)
        plan_raw = self.store.get_artifact(job_id, Stage.PLAN, "plan")
        sources_raw = self.store.get_artifact(job_id, Stage.SOURCES, "sources")
        outline_raw = self.store.get_artifact(job_id, Stage.OUTLINE, "outline")
        state = self.store.get_job(job_id)
        return GateContext(
            brief=brief,
            plan=ResearchPlan.model_validate(plan_raw) if plan_raw else None,
            registry=SourceRegistry.model_validate(sources_raw) if sources_raw else None,
            outline=DocumentOutline.model_validate(outline_raw) if outline_raw else None,
            fixture_mode=bool(getattr(self.provider, "fixture_mode", False)),
            current_year=state.created_at.year,
            human_overrides=list(state.data.get("overrides", [])),
        )

    def _load_artifact(self, job_id: str, stage: Stage, task_key: str, schema: type[T]) -> T:
        raw = self.store.get_artifact(job_id, stage, task_key)
        if raw is None:
            raise RuntimeError(f"Required artifact missing: {stage.value}/{task_key}")
        return schema.model_validate(raw)

    def _sections_for_job(self, job_id: str) -> list[SectionDraft]:
        state = self.store.get_job(job_id)
        completed = state.data.get("completed_sections", {})
        sections: list[SectionDraft] = []
        for section_key, pointer in completed.items():
            task_key = pointer["task_key"]
            attempt = int(pointer["attempt"])
            raw = self.store.get_artifact(job_id, Stage.WRITE, task_key, attempt)
            if raw is not None:
                sections.append(SectionDraft.model_validate(raw))
        outline = self.store.get_artifact(job_id, Stage.OUTLINE, "outline")
        if outline:
            order = {
                node.node_id: index
                for index, node in enumerate(DocumentOutline.model_validate(outline).nodes)
            }
            sections.sort(key=lambda section: order.get(section.section_id, 9999))
        return sections
