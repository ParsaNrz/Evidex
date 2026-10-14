from __future__ import annotations

from evidex.gates import (
    GateContext,
    intake_gate,
    outline_gate,
    output_gate,
    planning_gate,
    review_gate,
    section_gate,
    source_gate,
)
from evidex.models import (
    DocumentOutline,
    ExportPackage,
    ProjectBrief,
    ResearchPlan,
    ReviewReport,
    SectionDraft,
    SourceRegistry,
)


def _context(brief, artifacts) -> GateContext:
    return GateContext(
        brief=brief,
        plan=ResearchPlan.model_validate(artifacts["plan"]),
        registry=SourceRegistry.model_validate(artifacts["registry"]),
        outline=DocumentOutline.model_validate(artifacts["outline"]),
        fixture_mode=True,
        current_year=2026,
    )


def test_intake_gate_passes_and_flags_vague_topics(brief):
    result = intake_gate(brief, GateContext(brief=brief, current_year=2026))
    assert result.passed

    vague = ProjectBrief.model_validate({**brief.model_dump(mode="json"), "topic": "health"})
    failed = intake_gate(vague, GateContext(brief=vague, current_year=2026))
    assert not failed.passed
    assert "topic_specificity" in {check.check_id for check in failed.checks if not check.passed}
    assert failed.feedback_for_retry


def test_plan_gate_checks_objective_mapping(brief, fake_artifacts):
    context = _context(brief, fake_artifacts)
    plan = ResearchPlan.model_validate(fake_artifacts["plan"])
    assert planning_gate(plan, context).passed

    bad_data = plan.model_dump(mode="json")
    bad_data["objectives"][0]["question_ids"] = []
    failed = planning_gate(ResearchPlan.model_validate(bad_data), context)
    assert not failed.passed
    assert any(
        check.check_id == "objective_question_mapping" and not check.passed
        for check in failed.checks
    )


def test_source_gate_requires_distinct_verified_covered_sources(brief, fake_artifacts):
    context = _context(brief, fake_artifacts)
    registry = SourceRegistry.model_validate(fake_artifacts["registry"])
    assert source_gate(registry, context).passed
    production_context = GateContext(
        brief=brief,
        plan=context.plan,
        registry=registry,
        outline=context.outline,
        fixture_mode=False,
        current_year=2026,
    )
    assert not source_gate(registry, production_context).passed

    bad_data = registry.model_dump(mode="json")
    bad_data["sources"][1] = bad_data["sources"][0]
    failed = source_gate(SourceRegistry.model_validate(bad_data), context)
    assert not failed.passed
    failed_ids = {check.check_id for check in failed.checks if not check.passed}
    assert "unique_source_ids" in failed_ids
    assert "deduplicated_metadata" in failed_ids


def test_outline_gate_requires_template_coverage_and_word_budget(brief, fake_artifacts):
    context = _context(brief, fake_artifacts)
    outline = DocumentOutline.model_validate(fake_artifacts["outline"])
    assert outline_gate(outline, context).passed

    bad_data = outline.model_dump(mode="json")
    bad_data["nodes"][0]["word_budget"] += 1000
    failed = outline_gate(DocumentOutline.model_validate(bad_data), context)
    assert not failed.passed
    assert any(
        check.check_id == "word_budget_total" and not check.passed for check in failed.checks
    )

    missing_data = outline.model_dump(mode="json")
    missing_data["nodes"] = missing_data["nodes"][1:]
    missing = outline_gate(DocumentOutline.model_validate(missing_data), context)
    assert any(
        check.check_id == "required_template" and not check.passed for check in missing.checks
    )


def test_section_gate_accepts_traceable_claim_and_rejects_fake_citation(brief, fake_artifacts):
    context = _context(brief, fake_artifacts)
    outline = DocumentOutline.model_validate(fake_artifacts["outline"])
    registry = SourceRegistry.model_validate(fake_artifacts["registry"])
    node = next(item for item in outline.nodes if item.title == "Problem Statement")
    draft = SectionDraft.model_validate(
        fake_artifacts["fake"]._section(
            {
                "brief": brief.model_dump(mode="json"),
                "node": node.model_dump(mode="json"),
                "registry": registry.model_dump(mode="json"),
            }
        )
    )
    assert section_gate(draft, node, context).passed

    production_context = GateContext(
        brief=brief,
        plan=context.plan,
        registry=registry,
        outline=outline,
        fixture_mode=False,
        current_year=2026,
    )
    fixture_rejected = section_gate(draft, node, production_context)
    assert any(
        check.check_id == "source_verification" and not check.passed
        for check in fixture_rejected.checks
    )

    bad_draft = draft.model_copy(
        update={"body": draft.body.replace("[@fixture-001]", "[@fake-source-999]")}
    )
    failed = section_gate(bad_draft, node, context)
    assert not failed.passed
    assert any(
        check.check_id == "citation_keys_registered" and not check.passed for check in failed.checks
    )


def test_section_gate_allows_explicit_student_data_placeholder(brief):
    from evidex.models import DocumentType
    from evidex.providers import FakeLLM

    article = ProjectBrief.model_validate(
        {
            **brief.model_dump(mode="json"),
            "document_type": DocumentType.ARTICLE.value,
            "target_words": 5000,
        }
    )
    fake = FakeLLM()
    plan_data = fake._plan({"brief": article.model_dump(mode="json")})
    registry_data = fake._sources({"brief": article.model_dump(mode="json"), "plan": plan_data})
    outline_data = fake._outline(
        {"brief": article.model_dump(mode="json"), "plan": plan_data, "registry": registry_data}
    )
    artifacts = {"plan": plan_data, "registry": registry_data, "outline": outline_data}
    context = _context(article, artifacts)
    outline = DocumentOutline.model_validate(outline_data)
    results_node = next(item for item in outline.nodes if "Results" in item.title)
    placeholder = SectionDraft(
        section_id=results_node.node_id,
        title=results_node.title,
        language=article.language,
        body="[STUDENT_DATA: Add your analyzed findings here.]",
        claims=[],
    )
    assert section_gate(placeholder, results_node, context).passed


def test_review_gate_requires_citation_reference_match_and_returns_code_routes(
    brief, fake_artifacts
):
    context = _context(brief, fake_artifacts)
    node = context.outline.nodes[1]
    draft = SectionDraft.model_validate(
        fake_artifacts["fake"]._section(
            {
                "brief": brief.model_dump(mode="json"),
                "node": node.model_dump(mode="json"),
                "registry": context.registry.model_dump(mode="json"),
            }
        )
    )
    report = ReviewReport(
        summary="Review complete.",
        cited_source_ids=draft.claims[0].source_ids,
        reference_source_ids=draft.claims[0].source_ids,
    )
    assert review_gate(report, context, [draft]).passed

    bad_report = report.model_copy(update={"reference_source_ids": []})
    failed = review_gate(bad_report, context, [draft])
    assert not failed.passed
    assert any(
        check.check_id == "citation_reference_match" and not check.passed for check in failed.checks
    )

    routed_report = ReviewReport.model_validate(
        {
            **report.model_dump(mode="json"),
            "issues": [
                {
                    "issue_id": "issue-1",
                    "severity": "error",
                    "description": "Revise this section.",
                    "target_sections": [node.node_id],
                }
            ],
        }
    )
    routed = review_gate(routed_report, context, [draft])
    assert not routed.passed
    assert routed.route_to and routed.route_to[0].section_id == node.node_id


def test_output_gate_requires_complete_citation_audit(brief, fake_artifacts):
    context = _context(brief, fake_artifacts)
    node = next(item for item in context.outline.nodes if item.title == "Problem Statement")
    section = SectionDraft.model_validate(
        fake_artifacts["fake"]._section(
            {
                "brief": brief.model_dump(mode="json"),
                "node": node.model_dump(mode="json"),
                "registry": context.registry.model_dump(mode="json"),
            }
        )
    )
    package = ExportPackage.model_validate(
        fake_artifacts["fake"]._output(
            {
                "sections": [section.model_dump(mode="json")],
                "registry": context.registry.model_dump(mode="json"),
            }
        )
    )
    assert output_gate(package, context, [section]).passed

    bad_package = package.model_copy(update={"citation_audit": [], "audit_complete": False})
    failed = output_gate(bad_package, context, [section])
    assert not failed.passed
    assert any(
        check.check_id == "citation_audit_complete" and not check.passed for check in failed.checks
    )
