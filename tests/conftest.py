from __future__ import annotations

import pytest

from evidex.models import (
    CitationStyle,
    DataSituation,
    DegreeLevel,
    DocumentType,
    Language,
    ProjectBrief,
)
from evidex.providers import FakeLLM
from evidex.store import SQLiteStore


@pytest.fixture
def brief() -> ProjectBrief:
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


@pytest.fixture
def store(tmp_path) -> SQLiteStore:
    database = SQLiteStore(tmp_path / "evidex-test.sqlite3")
    yield database
    database.close()


@pytest.fixture
def fake_artifacts(brief):
    fake = FakeLLM()
    plan_data = fake._plan({"brief": brief.model_dump(mode="json")})
    registry_data = fake._sources({"brief": brief.model_dump(mode="json"), "plan": plan_data})
    outline_data = fake._outline(
        {
            "brief": brief.model_dump(mode="json"),
            "plan": plan_data,
            "registry": registry_data,
        }
    )
    return {
        "plan": plan_data,
        "registry": registry_data,
        "outline": outline_data,
        "fake": fake,
    }
