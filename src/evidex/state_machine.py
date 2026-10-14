from __future__ import annotations

from evidex.models import JobStatus, Stage

STAGE_ORDER: tuple[Stage, ...] = (
    Stage.INTAKE,
    Stage.PLAN,
    Stage.SOURCES,
    Stage.OUTLINE,
    Stage.WRITE,
    Stage.REVIEW,
    Stage.OUTPUT,
)

NEXT_STAGE: dict[Stage, Stage | None] = {
    Stage.INTAKE: Stage.PLAN,
    Stage.PLAN: Stage.SOURCES,
    Stage.SOURCES: Stage.OUTLINE,
    Stage.OUTLINE: Stage.WRITE,
    Stage.WRITE: Stage.REVIEW,
    Stage.REVIEW: Stage.OUTPUT,
    Stage.OUTPUT: None,
}

APPROVAL_STAGES = frozenset({Stage.PLAN, Stage.SOURCES, Stage.OUTLINE})

ALLOWED_STATUS_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.GATE_PASSED,
            JobStatus.GATE_FAILED,
            JobStatus.NEEDS_HUMAN,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.GATE_PASSED: frozenset(
        {
            JobStatus.RUNNING,
            JobStatus.AWAITING_APPROVAL,
            JobStatus.NEEDS_HUMAN,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.GATE_FAILED: frozenset(
        {JobStatus.RUNNING, JobStatus.NEEDS_HUMAN, JobStatus.CANCELLED}
    ),
    JobStatus.AWAITING_APPROVAL: frozenset(
        {JobStatus.RUNNING, JobStatus.NEEDS_HUMAN, JobStatus.CANCELLED}
    ),
    JobStatus.NEEDS_HUMAN: frozenset(
        {JobStatus.RUNNING, JobStatus.GATE_PASSED, JobStatus.CANCELLED}
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when an application command attempts an illegal workflow transition."""


def assert_status_transition(current: JobStatus, target: JobStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise InvalidTransition(f"Illegal job status transition: {current.value} -> {target.value}")


def assert_stage_transition(
    current: Stage | None,
    target: Stage | None,
    *,
    review_routed: bool = False,
) -> None:
    if current == target:
        return
    if current is None:
        if target == Stage.INTAKE:
            return
        raise InvalidTransition("A new pipeline must start at intake")
    expected = NEXT_STAGE[current]
    if target == expected:
        return
    if current == Stage.REVIEW and target == Stage.WRITE and review_routed:
        return
    raise InvalidTransition(
        f"Illegal stage transition: {current.value} -> {target.value if target else 'terminal'}"
    )
