from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from math import ceil
from typing import Any

from evidex.models import (
    DocumentOutline,
    ExportPackage,
    GateResult,
    Language,
    OutlineNode,
    ProjectBrief,
    ResearchPlan,
    ReviewReport,
    RouteTarget,
    SectionDraft,
    SourceRecord,
    SourceRegistry,
    Stage,
    VerificationStatus,
)
from evidex.templates import default_word_range, document_template

CITATION_PATTERN = re.compile(r"\[@([A-Za-z0-9_-]+)\]")
PLACEHOLDER_PATTERN = re.compile(r"\[STUDENT_DATA:[^\]]+\]", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:[.,/]\d+)*(?:%|٪)?")


@dataclass(frozen=True)
class GateContext:
    brief: ProjectBrief
    plan: ResearchPlan | None = None
    registry: SourceRegistry | None = None
    outline: DocumentOutline | None = None
    fixture_mode: bool = False
    current_year: int = field(default_factory=lambda: date.today().year)
    human_overrides: list[dict[str, Any]] = field(default_factory=list)

    @property
    def year(self) -> int:
        return self.current_year


def word_count(text: str) -> int:
    without_citations = CITATION_PATTERN.sub("", text)
    return len(re.findall(r"\w+", without_citations, flags=re.UNICODE))


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def _result(
    gate_id: str,
    stage: Stage,
    checks: list[tuple[str, bool, str, list[str] | None]],
    *,
    route_to: list[RouteTarget] | None = None,
) -> GateResult:
    check_models = [
        {
            "check_id": check_id,
            "passed": passed,
            "severity": "error",
            "details": details,
            "evidence": evidence or [],
        }
        for check_id, passed, details, evidence in checks
    ]
    failed = [item for item in check_models if not item["passed"]]
    feedback = None
    if failed:
        feedback = "Fix these failed checks and regenerate only this stage: " + "; ".join(
            f"{item['check_id']}: {item['details']}" for item in failed
        )
    return GateResult(
        gate_id=gate_id,
        stage=stage,
        passed=not failed,
        checks=check_models,
        feedback_for_retry=feedback,
        route_to=route_to,
    )


def schema_failure(stage: Stage, error: str) -> GateResult:
    return _result(
        f"{stage.value}.schema",
        stage,
        [("schema_valid", False, f"Output did not match the required schema: {error}", [error])],
    )


def intake_gate(brief: ProjectBrief, context: GateContext) -> GateResult:
    topic_terms = re.findall(r"\w+", brief.topic, flags=re.UNICODE)
    minimum_terms = 5 if brief.degree_level.value == "msc" else 3
    low_topic = len(topic_terms) < minimum_terms
    min_words, max_words = default_word_range(brief)
    length_ok = min_words <= brief.target_words <= max_words
    checks = [
        (
            "required_fields",
            bool(brief.field.strip() and brief.methodology.strip()),
            "Field and methodology must be provided.",
            None,
        ),
        (
            "topic_specificity",
            not low_topic,
            f"Topic needs at least {minimum_terms} meaningful terms for {brief.degree_level.value.upper()} work.",
            [brief.topic],
        ),
        (
            "length_consistency",
            length_ok,
            f"Target length {brief.target_words} is outside the default {min_words}–{max_words} word range for this document type and degree.",
            [str(brief.target_words), f"{min_words}-{max_words}"],
        ),
        (
            "citation_style_supported",
            brief.citation_style.value in {"apa7", "ieee", "vancouver", "custom"},
            "Choose APA 7, IEEE, Vancouver, or a named custom style.",
            [brief.citation_style.value],
        ),
        (
            "custom_style_named",
            brief.citation_style.value != "custom" or bool(brief.custom_style_name),
            "A custom citation style needs a style name or ruleset.",
            [brief.custom_style_name or "missing"],
        ),
    ]
    return _result("intake.v1", Stage.INTAKE, checks)


def planning_gate(plan: ResearchPlan, context: GateContext) -> GateResult:
    question_id_list = [question.question_id for question in plan.research_questions]
    objective_id_list = [objective.objective_id for objective in plan.objectives]
    question_ids = set(question_id_list)
    objective_mappings_ok = (
        len(question_id_list) == len(question_ids)
        and len(objective_id_list) == len(set(objective_id_list))
        and bool(plan.objectives)
        and all(
            objective.question_ids and set(objective.question_ids).issubset(question_ids)
            for objective in plan.objectives
        )
    )
    objective_count_ok = len(plan.objectives) <= (
        8 if context.brief.degree_level.value == "msc" else 6
    )
    languages = {query.language for query in plan.search_queries}
    query_languages_ok = Language.ENGLISH in languages and (
        context.brief.language != Language.PERSIAN or Language.PERSIAN in languages
    )
    budgets_total = sum(plan.section_budgets.values())
    budget_ok = abs(budgets_total - context.brief.target_words) <= ceil(
        context.brief.target_words * 0.05
    )
    keyword_language_ok = bool(plan.keywords_en) and (
        context.brief.language != Language.PERSIAN or bool(plan.keywords_fa)
    )
    checks = [
        (
            "objective_question_mapping",
            objective_mappings_ok,
            "Every objective must map to at least one existing research question.",
            [objective.objective_id for objective in plan.objectives if not objective.question_ids],
        ),
        (
            "degree_scope",
            objective_count_ok and len(plan.subtopics) <= 12,
            "Reduce the objective or subtopic count to a realistic degree-level scope.",
            [f"objectives={len(plan.objectives)}", f"subtopics={len(plan.subtopics)}"],
        ),
        (
            "search_language_coverage",
            query_languages_ok,
            "Search queries must cover English and, for a Persian project, Persian.",
            sorted(language.value for language in languages),
        ),
        (
            "keyword_language_coverage",
            keyword_language_ok,
            "Keywords must include English and, for a Persian project, Persian terms.",
            [
                "keywords_en",
                "keywords_fa" if context.brief.language == Language.PERSIAN else "not_required",
            ],
        ),
        (
            "section_budget_total",
            budget_ok,
            "Section budgets must sum to the target length within five percent.",
            [f"sum={budgets_total}", f"target={context.brief.target_words}"],
        ),
        (
            "method_and_timeline",
            bool(plan.methodology_type.strip() and plan.timeline),
            "Specify a methodology type and a feasible timeline.",
            [plan.methodology_type],
        ),
        (
            "research_plan_content",
            bool(plan.problem_statement.strip() and plan.scope.strip() and plan.keywords_en),
            "Problem statement, scope, and English search keywords are required.",
            None,
        ),
    ]
    return _result("plan.v1", Stage.PLAN, checks)


def minimum_source_count(context: GateContext) -> int:
    brief = context.brief
    if brief.document_type.value == "proposal":
        return 15
    if brief.document_type.value == "article":
        return 25
    return 25 if brief.degree_level.value == "bsc" else 40


def _source_key(source: SourceRecord) -> str:
    if source.doi:
        return "doi:" + source.doi.strip().casefold().removeprefix("https://doi.org/")
    first_author = source.authors[0].strip().casefold() if source.authors else ""
    return f"title:{_normalise(source.title)}|author:{first_author}|year:{source.year}"


def source_gate(registry: SourceRegistry, context: GateContext) -> GateResult:
    ids = [source.source_id for source in registry.sources]
    unique_ids = len(ids) == len(set(ids))
    unique_metadata = len({_source_key(source) for source in registry.sources}) == len(
        registry.sources
    )
    minimum = minimum_source_count(context)
    count_ok = len(registry.sources) >= minimum
    valid_statuses = {VerificationStatus.VERIFIED, VerificationStatus.STUDENT_CONFIRMED}
    if context.fixture_mode:
        valid_statuses.add(VerificationStatus.FIXTURE)
    verification_ok = all(
        source.verification.status in valid_statuses for source in registry.sources
    )
    not_retracted = all(
        not source.retracted and source.verification.status != VerificationStatus.RETRACTED
        for source in registry.sources
    )
    note_ids = [note.note_id for source in registry.sources for note in source.notes]
    unique_note_ids = len(note_ids) == len(set(note_ids))
    notes_ok = all(
        source.notes
        and all(note.paraphrase.strip() and note.locator.strip() for note in source.notes)
        for source in registry.sources
    )
    current_year = context.year
    recent = sum(source.year >= current_year - 10 for source in registry.sources)
    recency_ok = not registry.sources or recent / len(registry.sources) >= 0.5
    source_ids = set(ids)
    plan_subtopics = context.plan.subtopics if context.plan else list(registry.subtopic_sources)
    coverage_ok = bool(plan_subtopics) and all(
        len(set(registry.subtopic_sources.get(subtopic, [])) & source_ids) >= 2
        for subtopic in plan_subtopics
    )
    coverage_evidence = [
        f"{subtopic}: {len(set(registry.subtopic_sources.get(subtopic, [])) & source_ids)}"
        for subtopic in plan_subtopics
    ]
    coverage_refs_ok = all(
        set(source_list).issubset(source_ids) for source_list in registry.subtopic_sources.values()
    )
    checks = [
        (
            "minimum_source_count",
            count_ok,
            f"At least {minimum} distinct sources are required.",
            [f"found={len(registry.sources)}"],
        ),
        ("unique_source_ids", unique_ids, "Source registry IDs must be unique.", ids),
        (
            "deduplicated_metadata",
            unique_metadata,
            "Duplicate DOI or title/author/year records must be removed.",
            None,
        ),
        (
            "verification_status",
            verification_ok,
            "Every source must be verified or individually student-confirmed; fixture sources are test-only.",
            [
                source.source_id
                for source in registry.sources
                if source.verification.status not in valid_statuses
            ],
        ),
        (
            "retraction_check",
            not_retracted,
            "Retracted or withdrawn sources cannot be used.",
            [source.source_id for source in registry.sources if source.retracted],
        ),
        (
            "evidence_notes",
            notes_ok,
            "Every source needs at least one paraphrased note and locator.",
            [source.source_id for source in registry.sources if not source.notes],
        ),
        (
            "unique_evidence_note_ids",
            unique_note_ids,
            "Evidence note IDs must be globally unique within a registry.",
            note_ids,
        ),
        (
            "recency_mix",
            recency_ok,
            "At least half of the sources should be from the last ten years, except for justified seminal works.",
            [f"recent={recent}/{len(registry.sources)}"],
        ),
        (
            "subtopic_coverage",
            coverage_ok,
            "Each planned subtopic needs at least two relevant sources.",
            coverage_evidence,
        ),
        (
            "coverage_ids_exist",
            coverage_refs_ok,
            "Subtopic coverage must only reference registry IDs.",
            None,
        ),
    ]
    return _result("sources.v1", Stage.SOURCES, checks)


def outline_gate(outline: DocumentOutline, context: GateContext) -> GateResult:
    if context.plan is None or context.registry is None:
        return _result(
            "outline.v1",
            Stage.OUTLINE,
            [
                (
                    "stage_context",
                    False,
                    "Approved plan and source registry are required before outline validation.",
                    None,
                )
            ],
        )
    required_sections = [section.title for section in document_template(context.brief)]
    actual_titles = [node.title for node in outline.nodes]
    normalized_actual = [_normalise(title) for title in actual_titles]
    required_in_order = [_normalise(title) for title in required_sections]
    section_positions: list[int] = []
    for title in required_in_order:
        try:
            section_positions.append(normalized_actual.index(title))
        except ValueError:
            section_positions.append(-1)
    template_ok = all(
        position >= 0 for position in section_positions
    ) and section_positions == sorted(section_positions)
    node_ids = [node.node_id for node in outline.nodes]
    unique_nodes = len(node_ids) == len(set(node_ids))
    question_ids = {question.question_id for question in context.plan.research_questions}
    objective_ids = {objective.objective_id for objective in context.plan.objectives}
    covered_questions = {question for node in outline.nodes for question in node.question_ids}
    covered_objectives = {objective for node in outline.nodes for objective in node.objective_ids}
    objective_coverage_ok = question_ids.issubset(covered_questions) and objective_ids.issubset(
        covered_objectives
    )
    total_budget = sum(node.word_budget for node in outline.nodes)
    budget_ok = abs(total_budget - context.brief.target_words) <= ceil(
        context.brief.target_words * 0.05
    )
    registry_ids = {source.source_id for source in context.registry.sources}
    assigned_ids = {source_id for node in outline.nodes for source_id in node.source_ids}
    dropped_ids = {item.source_id for item in outline.dropped_sources}
    dropped_valid = all(item.reason.strip() for item in outline.dropped_sources)
    source_assignment_ok = registry_ids == (assigned_ids | dropped_ids) and not (
        assigned_ids & dropped_ids
    )
    source_ids_valid = assigned_ids.issubset(registry_ids) and dropped_ids.issubset(registry_ids)
    checks = [
        (
            "required_template",
            template_ok,
            "Outline must include all required template sections in order.",
            [title for title, pos in zip(required_sections, section_positions) if pos < 0],
        ),
        ("unique_outline_nodes", unique_nodes, "Outline node IDs must be unique.", node_ids),
        (
            "objective_question_coverage",
            objective_coverage_ok,
            "Every research question and objective must be addressed by at least one node.",
            sorted((question_ids - covered_questions) | (objective_ids - covered_objectives)),
        ),
        (
            "word_budget_total",
            budget_ok,
            "Outline budgets must total the target length within five percent.",
            [f"sum={total_budget}", f"target={context.brief.target_words}"],
        ),
        (
            "source_assignments_complete",
            source_assignment_ok and dropped_valid,
            "Every source must be assigned or explicitly dropped with a reason, but not both.",
            sorted(registry_ids - (assigned_ids | dropped_ids)),
        ),
        (
            "source_ids_valid",
            source_ids_valid,
            "Outline assignments must reference only registry source IDs.",
            sorted((assigned_ids | dropped_ids) - registry_ids),
        ),
    ]
    return _result("outline.v1", Stage.OUTLINE, checks)


def _allowed_source(source: SourceRecord, fixture_mode: bool) -> bool:
    if source.retracted or source.verification.status == VerificationStatus.RETRACTED:
        return False
    if source.verification.status in {
        VerificationStatus.VERIFIED,
        VerificationStatus.STUDENT_CONFIRMED,
    }:
        return True
    return fixture_mode and source.verification.status == VerificationStatus.FIXTURE


def _numbers(text: str) -> set[str]:
    text = PLACEHOLDER_PATTERN.sub("", text)
    text = CITATION_PATTERN.sub("", text)
    return {number.replace(",", ".") for number in NUMBER_PATTERN.findall(text)}


def section_gate(
    draft: SectionDraft,
    node: OutlineNode,
    context: GateContext,
) -> GateResult:
    if context.registry is None:
        return _result(
            "write.v1",
            Stage.WRITE,
            [("registry_available", False, "Source registry is required.", None)],
        )
    source_map = {source.source_id: source for source in context.registry.sources}
    note_map = {
        note.note_id: (source.source_id, note)
        for source in context.registry.sources
        for note in source.notes
    }
    budget = node.word_budget
    actual_words = word_count(draft.body)
    placeholder_only = bool(PLACEHOLDER_PATTERN.search(draft.body)) and not draft.claims
    budget_ok = placeholder_only or budget == 0 or abs(actual_words - budget) <= ceil(budget * 0.15)
    body_norm = _normalise(draft.body)
    claim_texts_present = all(_normalise(claim.text) in body_norm for claim in draft.claims)
    unknown_keys = sorted(set(CITATION_PATTERN.findall(draft.body)) - set(source_map))
    citation_keys = set(CITATION_PATTERN.findall(draft.body))
    claim_source_ids = {source_id for claim in draft.claims for source_id in claim.source_ids}
    claim_citations_ok = all(
        set(claim.source_ids).issubset(citation_keys) for claim in draft.claims
    )
    no_unlinked_citations = citation_keys.issubset(claim_source_ids)
    all_claims_cited = all(claim.source_ids and claim.evidence_note_ids for claim in draft.claims)
    valid_claim_source_ids = all(
        source_id in source_map and _allowed_source(source_map[source_id], context.fixture_mode)
        for claim in draft.claims
        for source_id in claim.source_ids
    )
    valid_evidence_notes = all(
        note_id in note_map and note_map[note_id][0] in claim.source_ids
        for claim in draft.claims
        for note_id in claim.evidence_note_ids
    )
    supported_claims = True
    weak_claims: list[str] = []
    for claim in draft.claims:
        matched_notes = [
            note_map[note_id][1]
            for note_id in claim.evidence_note_ids
            if note_id in note_map and note_map[note_id][0] in claim.source_ids
        ]
        claim_terms = set(_normalise(claim.text).split())
        note_terms = (
            set().union(*(set(_normalise(note.paraphrase).split()) for note in matched_notes))
            if matched_notes
            else set()
        )
        overlap = len(claim_terms & note_terms) / max(1, len(claim_terms))
        if overlap < 0.25:
            supported_claims = False
            weak_claims.append(claim.claim_id)
    traced_numbers: set[str] = set()
    for claim in draft.claims:
        for note_id in claim.evidence_note_ids:
            note_entry = note_map.get(note_id)
            if note_entry and note_entry[0] in claim.source_ids:
                traced_numbers |= _numbers(note_entry[1].paraphrase)
        for source_id in claim.source_ids:
            source = source_map.get(source_id)
            if source and source.abstract:
                traced_numbers |= _numbers(source.abstract)
    body_numbers = _numbers(draft.body)
    numbers_ok = body_numbers.issubset(traced_numbers)
    language_ok = draft.language == context.brief.language
    checks = [
        (
            "section_word_budget",
            budget_ok,
            f"Section should contain {budget} words ±15%; found {actual_words}.",
            [f"budget={budget}", f"actual={actual_words}"],
        ),
        (
            "citation_keys_registered",
            not unknown_keys,
            "Every inline citation key must exist in the source registry.",
            unknown_keys,
        ),
        (
            "claims_have_citations",
            all_claims_cited and claim_citations_ok and no_unlinked_citations,
            "Every factual claim must carry registered source IDs that also appear inline; every inline key must support a structured claim.",
            [
                claim.claim_id
                for claim in draft.claims
                if not claim.source_ids or not set(claim.source_ids).issubset(citation_keys)
            ]
            + sorted(citation_keys - claim_source_ids),
        ),
        (
            "source_verification",
            valid_claim_source_ids,
            "Cited sources must be verified or explicitly student-confirmed.",
            [
                source_id
                for claim in draft.claims
                for source_id in claim.source_ids
                if source_id not in source_map
                or not _allowed_source(source_map[source_id], context.fixture_mode)
            ],
        ),
        (
            "evidence_note_links",
            valid_evidence_notes,
            "Every claim must point to evidence notes belonging to its cited sources.",
            [
                claim.claim_id
                for claim in draft.claims
                if any(
                    note_id not in note_map or note_map[note_id][0] not in claim.source_ids
                    for note_id in claim.evidence_note_ids
                )
            ],
        ),
        (
            "claim_evidence_overlap",
            supported_claims,
            "Claim wording is not sufficiently supported by its linked evidence-note paraphrase.",
            weak_claims,
        ),
        (
            "numbers_traceable",
            numbers_ok,
            "Numbers must trace to evidence notes or be marked as [STUDENT_DATA: ...].",
            sorted(body_numbers - traced_numbers),
        ),
        (
            "claims_present_in_body",
            claim_texts_present,
            "Structured claims must appear in the section body.",
            [claim.claim_id for claim in draft.claims if _normalise(claim.text) not in body_norm],
        ),
        (
            "language_matches",
            language_ok,
            "Section language must match the approved project language.",
            [draft.language.value, context.brief.language.value],
        ),
    ]
    return _result("write.v1", Stage.WRITE, checks)


def review_gate(
    report: ReviewReport,
    context: GateContext,
    sections: list[SectionDraft],
) -> GateResult:
    if context.registry is None or context.outline is None:
        return _result(
            "review.v1",
            Stage.REVIEW,
            [("review_context", False, "Source registry and outline are required.", None)],
        )
    actual_cited = {
        source_id
        for section in sections
        for claim in section.claims
        for source_id in claim.source_ids
    }
    registry_ids = {source.source_id for source in context.registry.sources}
    actual_cited_valid = actual_cited.issubset(registry_ids)
    cited_match = set(report.cited_source_ids) == actual_cited
    references_match = set(report.reference_source_ids) == actual_cited
    refs_unique = len(report.reference_source_ids) == len(set(report.reference_source_ids))
    routable_sections = {node.node_id for node in context.outline.nodes if node.word_budget > 0}
    unknown_targets = {
        target
        for issue in report.issues
        for target in issue.target_sections
        if target not in routable_sections
    }
    routes = [
        RouteTarget(section_id=target, reason=issue.description)
        for issue in report.issues
        for target in issue.target_sections
        if target not in unknown_targets
    ]
    unique_routes = {route.section_id: route for route in routes}
    no_issues = not report.issues
    checks = [
        (
            "citation_registry_integrity",
            actual_cited_valid,
            "Every cited source must exist in the registry.",
            sorted(actual_cited - registry_ids),
        ),
        (
            "citation_reference_match",
            cited_match and references_match and refs_unique,
            "In-text citation IDs and reference IDs must match one-to-one with no duplicates.",
            [
                f"cited={sorted(report.cited_source_ids)}",
                f"references={sorted(report.reference_source_ids)}",
                f"actual={sorted(actual_cited)}",
            ],
        ),
        (
            "review_findings",
            no_issues,
            "Resolve review findings before output.",
            [issue.issue_id for issue in report.issues],
        ),
        (
            "review_targets_valid",
            not unknown_targets,
            "Review routing may target only known outline sections.",
            sorted(unknown_targets),
        ),
        ("review_summary", bool(report.summary.strip()), "Review summary must be present.", None),
    ]
    route_to = list(unique_routes.values()) or None
    return _result("review.v1", Stage.REVIEW, checks, route_to=route_to)


def output_gate(
    package: ExportPackage, context: GateContext, sections: list[SectionDraft]
) -> GateResult:
    if context.registry is None:
        return _result(
            "output.v1",
            Stage.OUTPUT,
            [("output_context", False, "Source registry is required.", None)],
        )
    source_map = {source.source_id: source for source in context.registry.sources}
    claims_by_source: dict[str, list[str]] = {}
    notes_by_source: dict[str, list[str]] = {}
    for section in sections:
        for claim in section.claims:
            for source_id in claim.source_ids:
                claims_by_source.setdefault(source_id, []).append(claim.claim_id)
                notes_by_source.setdefault(source_id, []).extend(claim.evidence_note_ids)
    audit_map = {entry.source_id: entry for entry in package.citation_audit}
    audit_ids_match_citations = set(audit_map) == set(claims_by_source) and len(audit_map) == len(
        package.citation_audit
    )
    audit_complete = (
        audit_ids_match_citations
        and all(
            source_id in audit_map
            and set(audit_map[source_id].claim_ids) >= set(claim_ids)
            and set(audit_map[source_id].evidence_note_ids)
            >= set(notes_by_source.get(source_id, []))
            and audit_map[source_id].verification_status
            == source_map[source_id].verification.status
            for source_id, claim_ids in claims_by_source.items()
            if source_id in source_map
        )
        and all(source_id in source_map for source_id in claims_by_source)
    )
    demo_mode_ok = package.demo_mode == context.fixture_mode
    override_log_ok = package.human_overrides == context.human_overrides
    file_records_ok = package.demo_mode or (
        any(file.format.casefold() == "docx" for file in package.files)
        and any(file.format.casefold() == "pdf" for file in package.files)
        and all(file.size_bytes > 0 for file in package.files)
    )
    paths_unique = len({file.path for file in package.files}) == len(package.files)
    checks = [
        (
            "citation_audit_complete",
            package.audit_complete and audit_complete,
            "Every cited claim must map to a registry source, verification status, and evidence note in the audit.",
            sorted(set(claims_by_source) - set(audit_map))
            + sorted(set(audit_map) - set(claims_by_source)),
        ),
        (
            "demo_mode_label",
            demo_mode_ok,
            "Package demo flag must be set by the execution mode, not asserted by generated prose.",
            [f"package={package.demo_mode}", f"fixture={context.fixture_mode}"],
        ),
        (
            "human_overrides_audited",
            override_log_ok,
            "Every persisted human override must be included in the final citation audit package.",
            [
                f"expected={len(context.human_overrides)}",
                f"reported={len(package.human_overrides)}",
            ],
        ),
        (
            "export_files_valid",
            file_records_ok,
            "A production package must contain non-empty DOCX and PDF files; fixture runs are clearly marked demo-only.",
            [file.format for file in package.files],
        ),
        (
            "export_paths_unique",
            paths_unique,
            "Export file paths must be unique.",
            [file.path for file in package.files],
        ),
    ]
    return _result("output.v1", Stage.OUTPUT, checks)


def evaluate_gate(
    stage: Stage,
    output: Any,
    context: GateContext,
    *,
    section_node: OutlineNode | None = None,
    sections: list[SectionDraft] | None = None,
) -> GateResult:
    if stage == Stage.INTAKE:
        return intake_gate(output, context)
    if stage == Stage.PLAN:
        return planning_gate(output, context)
    if stage == Stage.SOURCES:
        return source_gate(output, context)
    if stage == Stage.OUTLINE:
        return outline_gate(output, context)
    if stage == Stage.WRITE:
        if section_node is None:
            return _result(
                "write.v1",
                Stage.WRITE,
                [("section_spec", False, "A section outline node is required.", None)],
            )
        return section_gate(output, section_node, context)
    if stage == Stage.REVIEW:
        return review_gate(output, context, sections or [])
    if stage == Stage.OUTPUT:
        return output_gate(output, context, sections or [])
    raise ValueError(f"No gate is registered for stage {stage.value}")
