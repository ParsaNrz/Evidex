from __future__ import annotations

import pytest

from evidex.models import JobStatus, Stage
from evidex.state_machine import (
    InvalidTransition,
    assert_stage_transition,
    assert_status_transition,
)


def test_state_machine_has_fixed_order():
    assert_stage_transition(Stage.INTAKE, Stage.PLAN)
    assert_stage_transition(Stage.PLAN, Stage.SOURCES)
    assert_stage_transition(Stage.SOURCES, Stage.OUTLINE)
    assert_stage_transition(Stage.OUTLINE, Stage.WRITE)
    assert_stage_transition(Stage.WRITE, Stage.REVIEW)
    assert_stage_transition(Stage.REVIEW, Stage.OUTPUT)
    assert_stage_transition(Stage.OUTPUT, None)


def test_state_machine_rejects_skipping_and_unapproved_review_route():
    with pytest.raises(InvalidTransition):
        assert_stage_transition(Stage.INTAKE, Stage.SOURCES)
    with pytest.raises(InvalidTransition):
        assert_stage_transition(Stage.REVIEW, Stage.WRITE)


def test_only_code_selected_review_route_can_return_to_writing():
    assert_stage_transition(Stage.REVIEW, Stage.WRITE, review_routed=True)


def test_terminal_status_cannot_be_resumed():
    with pytest.raises(InvalidTransition):
        assert_status_transition(JobStatus.COMPLETED, JobStatus.RUNNING)
