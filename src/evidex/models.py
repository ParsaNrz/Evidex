from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DocumentType(StrEnum):
    ARTICLE = "article"
    PROPOSAL = "proposal"
    THESIS = "thesis"


class ArticleFormat(StrEnum):
    IMRAD = "imrad"
    REVIEW = "review"


class DegreeLevel(StrEnum):
    BSC = "bsc"
    MSC = "msc"


class Language(StrEnum):
    PERSIAN = "fa"
    ENGLISH = "en"


class CitationStyle(StrEnum):
    APA7 = "apa7"
    IEEE = "ieee"
    VANCOUVER = "vancouver"
    CUSTOM = "custom"


class DataSituation(StrEnum):
    HAS_DATA = "has_data"
    WILL_COLLECT = "will_collect"
    NO_DATA = "no_data"


class Stage(StrEnum):
    INTAKE = "intake"
    PLAN = "plan"
    SOURCES = "sources"
    OUTLINE = "outline"
    WRITE = "write"
    REVIEW = "review"
    OUTPUT = "output"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    GATE_PASSED = "GATE_PASSED"
    GATE_FAILED = "GATE_FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    STUDENT_CONFIRMED = "student_confirmed"
    UNVERIFIED = "unverified"
    RETRACTED = "retracted"
    FIXTURE = "fixture"


class SourceOrigin(StrEnum):
    API = "api"
    USER_PROVIDED = "user_provided"
    TEST_FIXTURE = "test_fixture"


class ProjectBrief(StrictModel):
    document_type: DocumentType
    article_format: ArticleFormat = ArticleFormat.IMRAD
    degree_level: DegreeLevel
    field: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=1000)
    language: Language
    citation_style: CitationStyle
    custom_style_name: str | None = Field(default=None, max_length=120)
    target_words: int = Field(gt=0, le=50000)
    university_template: str | None = Field(default=None, max_length=500)
    deadline: date | None = None
    methodology: str = Field(min_length=1, max_length=1000)
    data_situation: DataSituation
    user_provided_sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def custom_style_has_name(self) -> ProjectBrief:
        if self.citation_style == CitationStyle.CUSTOM and not self.custom_style_name:
            raise ValueError("custom_style_name is required when citation_style is custom")
        return self


class ResearchQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Objective(StrictModel):
    objective_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    question_ids: list[str] = Field(default_factory=list)


class SearchQuery(StrictModel):
    query: str = Field(min_length=1)
    language: Language


class TimelineItem(StrictModel):
    milestone: str = Field(min_length=1)
    duration_weeks: int = Field(gt=0, le=520)


class ResearchPlan(StrictModel):
    problem_statement: str = Field(min_length=1)
    research_questions: list[ResearchQuestion] = Field(min_length=1)
    objectives: list[Objective] = Field(min_length=1)
    scope: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    methodology_type: str = Field(min_length=1)
    keywords_fa: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(default_factory=list)
    search_queries: list[SearchQuery] = Field(min_length=1)
    subtopics: list[str] = Field(min_length=1)
    section_budgets: dict[str, int] = Field(default_factory=dict)
    timeline: list[TimelineItem] = Field(min_length=1)


class EvidenceNote(StrictModel):
    note_id: str = Field(min_length=1)
    paraphrase: str = Field(min_length=1)
    locator: str = Field(min_length=1)


class Verification(StrictModel):
    status: VerificationStatus
    method: str = Field(min_length=1)
    checked_at: datetime | None = None
    matched_fields: list[str] = Field(default_factory=list)


class SourceRecord(StrictModel):
    source_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1400, le=2200)
    venue: str | None = None
    volume_issue_pages: str | None = None
    doi: str | None = None
    url: str | None = None
    language: Language = Language.ENGLISH
    abstract: str | None = None
    oa_pdf_url: str | None = None
    origin: SourceOrigin
    verification: Verification
    relevance_score: float = Field(ge=0, le=1)
    retracted: bool = False
    notes: list[EvidenceNote] = Field(default_factory=list)


class SourceRegistry(StrictModel):
    sources: list[SourceRecord]
    subtopic_sources: dict[str, list[str]] = Field(default_factory=dict)
    gathered_at: datetime = Field(default_factory=utc_now)


class OutlineNode(StrictModel):
    node_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)
    objective_ids: list[str] = Field(default_factory=list)
    question_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    word_budget: int = Field(ge=0)
    parent_id: str | None = None


class DroppedSource(StrictModel):
    source_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class DocumentOutline(StrictModel):
    nodes: list[OutlineNode] = Field(min_length=1)
    dropped_sources: list[DroppedSource] = Field(default_factory=list)


class ClaimRecord(StrictModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    evidence_note_ids: list[str] = Field(min_length=1)


class SectionDraft(StrictModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    language: Language
    body: str = Field(min_length=1)
    claims: list[ClaimRecord] = Field(default_factory=list)


class ReviewIssue(StrictModel):
    issue_id: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target_sections: list[str] = Field(default_factory=list)


class ReviewReport(StrictModel):
    summary: str = Field(min_length=1)
    issues: list[ReviewIssue] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    reference_source_ids: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)


class CitationAuditEntry(StrictModel):
    source_id: str
    verification_status: VerificationStatus
    claim_ids: list[str] = Field(default_factory=list)
    evidence_note_ids: list[str] = Field(default_factory=list)


class ExportedFile(StrictModel):
    format: str
    path: str
    size_bytes: int = Field(ge=0)


class ExportPackage(StrictModel):
    files: list[ExportedFile] = Field(default_factory=list)
    citation_audit: list[CitationAuditEntry] = Field(default_factory=list)
    change_log: list[str] = Field(default_factory=list)
    human_overrides: list[dict[str, Any]] = Field(default_factory=list)
    ai_use_disclosure: str | None = None
    audit_complete: bool
    demo_mode: bool


class CheckResult(StrictModel):
    check_id: str
    passed: bool
    severity: str = "error"
    details: str
    evidence: list[str] = Field(default_factory=list)


class RouteTarget(StrictModel):
    section_id: str
    reason: str


class GateResult(StrictModel):
    gate_id: str
    stage: Stage
    passed: bool
    checks: list[CheckResult]
    feedback_for_retry: str | None = None
    route_to: list[RouteTarget] | None = None


class JobState(StrictModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    current_stage: Stage | None = Stage.INTAKE
    attempt: int = 0
    task_key: str | None = "intake"
    feedback_for_retry: str | None = None
    pending_approval: Stage | None = None
    section_queue: list[str] = Field(default_factory=list)
    section_cursor: int = 0
    review_cycle: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ModelCallRecord(StrictModel):
    call_id: str
    job_id: str
    stage: Stage
    task_key: str
    attempt: int
    provider: str
    model: str
    prompt_name: str
    prompt_version: str
    status: str
    input_hash: str
    idempotency_key: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
