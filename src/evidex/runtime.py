"""Explicit runtime selection: no silent fallback from live integrations to fixtures."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from evidex.integrations import CrossrefRetriever, OpenAIProvider
from evidex.models import Language, OutlineNode, ProjectBrief, ResearchPlan, SectionDraft, Stage
from evidex.providers import FakeLLM, LLMRequest, LLMResponse
from evidex.rendering import DocumentRenderer


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(".evidex")
    demo: bool = False
    secure_cookies: bool = True
    registration: bool = True
    llm_key: str = field(default="", repr=False)
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    crossref_mailto: str = ""
    pdf_font: str = ""  # Empty means "discover an installed Unicode TTF font".

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.getenv("EVIDEX_DATA_DIR", ".evidex")),
            demo=os.getenv("EVIDEX_DEMO", "0") == "1",
            secure_cookies=os.getenv("EVIDEX_SECURE_COOKIES", "1") == "1",
            registration=os.getenv("EVIDEX_REGISTRATION", "1") == "1",
            llm_key=os.getenv("EVIDEX_LLM_API_KEY", ""),
            llm_model=os.getenv("EVIDEX_LLM_MODEL", "gpt-4o-mini"),
            llm_base_url=os.getenv("EVIDEX_LLM_BASE_URL", "https://api.openai.com/v1"),
            crossref_mailto=os.getenv("EVIDEX_CROSSREF_MAILTO", ""),
            pdf_font=os.getenv("EVIDEX_PDF_FONT", ""),
        )


class IntegratedProvider:
    """Dispatch side-effect stages to code and generative stages to the chosen LLM."""

    def __init__(self, llm, retriever, renderer: DocumentRenderer):
        self.llm, self.retriever, self.renderer = llm, retriever, renderer
        self.fixture_mode = llm.fixture_mode
        self.name, self.model = llm.name, llm.model

    def complete_json(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        if request.stage == Stage.OUTPUT:
            output = self.renderer.render(
                request.job_id, request.input_payload, demo_mode=self.fixture_mode
            ).model_dump(mode="json")
            service = "document-renderer"
        elif request.stage == Stage.INTAKE:
            output = ProjectBrief.model_validate(request.input_payload["brief"]).model_dump(
                mode="json"
            )
            service = "intake-validation"
        elif (
            request.stage == Stage.WRITE
            and not self.fixture_mode
            and any(
                word in request.input_payload["node"]["title"].casefold()
                for word in ("results", "findings", "یافته", "نتایج")
            )
        ):
            # The intake flag HAS_DATA is not a dataset. Until uploads are implemented,
            # original findings are an application-owned placeholder, never model prose.
            node = OutlineNode.model_validate(request.input_payload["node"])
            brief = ProjectBrief.model_validate(request.input_payload["brief"])
            message = (
                "داده‌ها و تحلیل خود را اضافه کنید؛ هیچ مجموعه داده‌ای بارگذاری نشده است."
                if brief.language == Language.PERSIAN
                else "Add your dataset and analysis; no dataset has been uploaded."
            )
            output = SectionDraft(
                section_id=node.node_id,
                title=node.title,
                language=brief.language,
                body=f"[STUDENT_DATA: {message}]",
            ).model_dump(mode="json")
            service = "student-data-placeholder"
        elif request.stage == Stage.SOURCES and not self.fixture_mode:
            output = self.retriever.gather(
                ProjectBrief.model_validate(request.input_payload["brief"]),
                ResearchPlan.model_validate(request.input_payload["plan"]),
            ).model_dump(mode="json")
            service = "crossref"
        else:
            return self.llm.complete_json(request)
        return LLMResponse(
            output, service, "application-v1", 0, 0, int((time.perf_counter() - started) * 1000), 0
        )

    def close(self):
        for service in (self.llm, self.retriever):
            if hasattr(service, "close"):
                service.close()


def make_provider(settings: Settings, *, demo: bool | None = None) -> IntegratedProvider:
    demo = settings.demo if demo is None else demo
    llm = (
        FakeLLM()
        if demo
        else OpenAIProvider(settings.llm_key, settings.llm_model, settings.llm_base_url)
    )
    return IntegratedProvider(
        llm,
        None if demo else CrossrefRetriever(settings.crossref_mailto),
        DocumentRenderer(settings.data_dir / "exports", settings.pdf_font),
    )
