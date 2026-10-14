from __future__ import annotations

from dataclasses import dataclass

from evidex.models import ArticleFormat, DegreeLevel, DocumentType, ProjectBrief


@dataclass(frozen=True)
class TemplateSection:
    title: str
    substantive: bool = True


def document_template(brief: ProjectBrief) -> list[TemplateSection]:
    if brief.document_type == DocumentType.PROPOSAL:
        titles = [
            "Title",
            "Problem Statement",
            "Significance",
            "Objectives",
            "Research Questions/Hypotheses",
            "Concise Literature Review",
            "Methodology",
            "Timeline",
            "Expected Outcomes",
            "References",
        ]
        non_substantive = {"Title", "References"}
    elif brief.document_type == DocumentType.ARTICLE:
        if brief.article_format == ArticleFormat.REVIEW:
            titles = [
                "Title",
                "Abstract",
                "Keywords",
                "Introduction",
                "Search Methodology",
                "Thematic Synthesis",
                "Gaps",
                "Conclusion",
                "References",
            ]
        else:
            titles = [
                "Title",
                "Abstract",
                "Keywords",
                "Introduction",
                "Literature Review/Background",
                "Methods",
                "Results",
                "Discussion",
                "Conclusion",
                "References",
            ]
        non_substantive = {"Title", "References", "Keywords"}
    else:
        titles = [
            "Title Page",
            "Abstract (Persian)",
            "Abstract (English)",
            "Table of Contents",
            "List of Figures",
            "List of Tables",
            "Chapter 1: Introduction",
            "Chapter 2: Literature Review",
            "Chapter 3: Methodology",
            "Chapter 4: Results/Findings",
            "Chapter 5: Discussion",
            "Conclusion and Recommendations",
            "References",
            "Appendices",
        ]
        non_substantive = {
            "Title Page",
            "Abstract (Persian)",
            "Abstract (English)",
            "Table of Contents",
            "List of Figures",
            "List of Tables",
            "References",
            "Appendices",
        }
    return [TemplateSection(title, title not in non_substantive) for title in titles]


def default_word_range(brief: ProjectBrief) -> tuple[int, int]:
    if brief.document_type == DocumentType.PROPOSAL:
        return 2_000, 5_000
    if brief.document_type == DocumentType.ARTICLE:
        return 5_000, 8_000
    if brief.degree_level == DegreeLevel.BSC:
        return 8_000, 15_000
    return 15_000, 30_000


def distribute_words(brief: ProjectBrief) -> dict[str, int]:
    sections = [section.title for section in document_template(brief) if section.substantive]
    if not sections:
        return {}
    base, remainder = divmod(brief.target_words, len(sections))
    return {title: base + (1 if index < remainder else 0) for index, title in enumerate(sections)}


def section_id(title: str) -> str:
    slug = "-".join(
        part.lower() for part in "".join(char if char.isalnum() else " " for char in title).split()
    )
    return slug or "section"
