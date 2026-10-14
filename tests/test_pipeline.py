from __future__ import annotations

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
from evidex.runner import PipelineConfig, PipelineRunner
from evidex.store import SQLiteStore


def make_brief() -> ProjectBrief:
    return ProjectBrief(
        document_type=DocumentType.PROPOSAL,
        degree_level=DegreeLevel.BSC,
        field="Social sciences",
        topic="How social support relates to student mental health",
        language=Language.ENGLISH,
        citation_style=CitationStyle.APA7,
        target_words=3000,
        methodology="Scoping literature review",
        data_situation=DataSituation.NO_DATA,
    )


def approve_all_until_terminal(runner: PipelineRunner, job_id: str):
    state = runner.run(job_id)
    for _ in range(10):
        if state.status == JobStatus.AWAITING_APPROVAL:
            assert state.pending_approval is not None
            state = runner.approve(job_id, state.pending_approval, actor="test-student")
            state = runner.run(job_id)
            continue
        return state
    return state


def test_full_pipeline_retries_with_feedback_and_requires_approvals(store):
    fake = FakeLLM(fail_first_stages={Stage.PLAN.value})
    runner = PipelineRunner(store, fake)
    created = runner.create_project(make_brief())

    state = runner.run(created.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL
    assert state.pending_approval == Stage.PLAN
    assert state.current_stage == Stage.PLAN

    plan_attempts = [a for a in store.list_attempts(created.job_id) if a["stage"] == "plan"]
    assert [(item["attempt"], item["status"]) for item in plan_attempts] == [
        (1, "gate_failed"),
        (2, "passed"),
    ]
    plan_requests = [request for request in fake.calls if request.stage == Stage.PLAN]
    assert len(plan_requests) == 2
    assert plan_requests[0].feedback is None
    assert "objective_question_mapping" in plan_requests[1].feedback
    assert "objective_question_mapping" in plan_attempts[1]["input"]["retry_feedback"]
    assert store.get_gate_result(created.job_id, Stage.PLAN, "plan", 1).passed is False
    assert store.get_gate_result(created.job_id, Stage.PLAN, "plan", 2).passed is True

    state = runner.approve(created.job_id, Stage.PLAN, actor="test-student")
    assert state.status == JobStatus.RUNNING
    state = runner.run(created.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL
    assert state.pending_approval == Stage.SOURCES

    runner.approve(created.job_id, Stage.SOURCES, actor="test-student")
    state = runner.run(created.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL
    assert state.pending_approval == Stage.OUTLINE

    runner.approve(created.job_id, Stage.OUTLINE, actor="test-student")
    state = runner.run(created.job_id)
    assert state.status == JobStatus.COMPLETED
    assert state.current_stage is None

    assert [event["event_type"] for event in store.list_events(created.job_id)].count(
        "gate_failed"
    ) == 1
    assert [event["event_type"] for event in store.list_events(created.job_id)].count(
        "approval_accepted"
    ) == 3
    assert store.list_model_calls(created.job_id)
    assert all(call.prompt_version == "1" for call in store.list_model_calls(created.job_id))
    assert store.get_artifact(created.job_id, Stage.OUTPUT, "output") is not None
    assert len(state.data["completed_sections"]) == 8


def test_restart_resumes_from_persisted_checkpoint_without_repeating_work(tmp_path):
    db_path = tmp_path / "restart.sqlite3"
    first_store = SQLiteStore(db_path)
    first_runner = PipelineRunner(first_store, FakeLLM())
    job = first_runner.create_project(make_brief())
    state = first_runner.run(job.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL
    calls_before_restart = len(first_store.list_model_calls(job.job_id))
    first_store.close()

    second_store = SQLiteStore(db_path)
    second_fake = FakeLLM()
    second_runner = PipelineRunner(second_store, second_fake)
    resumed = second_runner.run(job.job_id)
    assert resumed.status == JobStatus.AWAITING_APPROVAL
    assert len(second_fake.calls) == 0
    second_runner.approve(job.job_id, Stage.PLAN, actor="resume-test")
    state = second_runner.run(job.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL
    assert state.pending_approval == Stage.SOURCES
    assert len(second_store.list_model_calls(job.job_id)) == calls_before_restart + 1
    assert len([a for a in second_store.list_attempts(job.job_id) if a["stage"] == "intake"]) == 1
    assert len([a for a in second_store.list_attempts(job.job_id) if a["stage"] == "plan"]) == 1
    second_store.close()


def test_retry_exhaustion_pauses_for_human_and_override_is_logged(store):
    base_config = PipelineConfig()
    max_attempts = dict(base_config.max_attempts)
    max_attempts[Stage.PLAN] = 1
    config = PipelineConfig(max_attempts=max_attempts)
    runner = PipelineRunner(store, FakeLLM(fail_first_stages={"plan"}), config=config)
    job = runner.create_project(make_brief())
    state = runner.run(job.job_id)

    assert state.status == JobStatus.NEEDS_HUMAN
    assert state.current_stage == Stage.PLAN
    assert "objective_question_mapping" in (state.feedback_for_retry or "")
    gate = store.get_gate_result(job.job_id, Stage.PLAN, "plan", 1)
    assert gate and not gate.passed

    state = runner.override_failed_checks(
        job.job_id,
        ["objective_question_mapping"],
        "Student reviewed and accepts the missing mapping for this demo.",
        actor="student-42",
    )
    assert state.status == JobStatus.AWAITING_APPROVAL
    assert state.pending_approval == Stage.PLAN
    assert state.data["overrides"][0]["check_ids"] == ["objective_question_mapping"]
    assert any(event["event_type"] == "gate_overridden" for event in store.list_events(job.job_id))
    assert not gate.passed  # The historical failed gate was not erased.

    runner.approve(job.job_id, Stage.PLAN, actor="test-student")
    state = runner.run(job.job_id)
    assert state.pending_approval == Stage.SOURCES
    runner.approve(job.job_id, Stage.SOURCES, actor="test-student")
    state = runner.run(job.job_id)
    assert state.pending_approval == Stage.OUTLINE
    runner.approve(job.job_id, Stage.OUTLINE, actor="test-student")
    state = runner.run(job.job_id)
    assert state.status == JobStatus.COMPLETED
    package = store.get_artifact(job.job_id, Stage.OUTPUT, "output")
    assert package["human_overrides"] == state.data["overrides"]


def test_review_failure_routes_only_the_code_selected_section(store):
    fake = FakeLLM(fail_first_stages={Stage.REVIEW.value})
    runner = PipelineRunner(store, fake)
    job = runner.create_project(make_brief())
    state = approve_all_until_terminal(runner, job.job_id)

    assert state.status == JobStatus.COMPLETED
    review_attempts = [a for a in store.list_attempts(job.job_id) if a["stage"] == "review"]
    assert [(item["attempt"], item["status"]) for item in review_attempts] == [
        (1, "gate_failed"),
        (2, "passed"),
    ]
    routed_writes = [
        attempt
        for attempt in store.list_attempts(job.job_id)
        if attempt["stage"] == "write" and "#review-1" in attempt["task_key"]
    ]
    assert len(routed_writes) == 1
    route_events = [
        event
        for event in store.list_events(job.job_id)
        if event["event_type"] == "review_routed_to_sections"
    ]
    assert len(route_events) == 1
    assert route_events[0]["payload"]["section_ids"] == ["problem-statement"]


def test_only_the_failing_section_is_retried(store):
    fake = FakeLLM(fail_first_tasks={"problem-statement"})
    runner = PipelineRunner(store, fake)
    job = runner.create_project(make_brief())
    state = approve_all_until_terminal(runner, job.job_id)

    assert state.status == JobStatus.COMPLETED
    writes = [attempt for attempt in store.list_attempts(job.job_id) if attempt["stage"] == "write"]
    problem_attempts = [attempt for attempt in writes if attempt["task_key"] == "problem-statement"]
    assert [(attempt["attempt"], attempt["status"]) for attempt in problem_attempts] == [
        (1, "gate_failed"),
        (2, "passed"),
    ]
    untouched = [attempt for attempt in writes if attempt["task_key"] != "problem-statement"]
    assert len(untouched) == 7
    assert all(attempt["attempt"] == 1 and attempt["status"] == "passed" for attempt in untouched)
    retry_request = next(
        request
        for request in fake.calls
        if request.stage == Stage.WRITE
        and request.task_key == "problem-statement"
        and request.attempt == 2
    )
    assert "citation_keys_registered" in retry_request.feedback


def test_wrong_checkpoint_cannot_be_approved(store):
    runner = PipelineRunner(store, FakeLLM())
    job = runner.create_project(make_brief())
    state = runner.run(job.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL
    try:
        runner.approve(job.job_id, Stage.SOURCES)
    except ValueError as exc:
        assert "not awaiting approval" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("Wrong approval stage was accepted")


def test_cancel_is_terminal(store):
    runner = PipelineRunner(store, FakeLLM())
    job = runner.create_project(make_brief())
    cancelled = runner.cancel(job.job_id)
    assert cancelled.status == JobStatus.CANCELLED
    assert runner.run(job.job_id).status == JobStatus.CANCELLED
