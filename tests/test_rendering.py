from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from pypdf import PdfReader

from evidex.models import Language, Stage
from evidex.providers import FakeLLM
from evidex.rendering import DEMO_WARNING, DocumentRenderer
from evidex.runner import PipelineRunner
from evidex.runtime import IntegratedProvider


@pytest.mark.parametrize("language", [Language.ENGLISH, Language.PERSIAN])
def test_export_files_open_have_disclosure_and_rtl(brief, store, tmp_path, language):
    brief.language = language
    if language == Language.PERSIAN:
        brief.topic = "رابطه حمایت اجتماعی با سلامت روان دانشجویان"
    provider = IntegratedProvider(FakeLLM(), None, DocumentRenderer(tmp_path / "exports"))
    runner = PipelineRunner(store, provider)
    job = runner.create_project(brief)
    for stage in [Stage.PLAN, Stage.SOURCES, Stage.OUTLINE]:
        state = runner.run(job.job_id)
        assert state.pending_approval == stage
        runner.approve(job.job_id, stage)
    state = runner.run(job.job_id)
    assert state.status == "COMPLETED", state.feedback_for_retry
    package = store.get_artifact(job.job_id, Stage.OUTPUT, "output")
    paths = {f["format"]: Path(f["path"]) for f in package["files"]}
    paragraphs = [p.text for p in Document(paths["docx"]).paragraphs]
    assert paragraphs[0] == brief.topic
    assert DEMO_WARNING in "\n".join(paragraphs)
    assert "[@fixture" not in "\n".join(paragraphs)
    assert paths["pdf"].read_bytes().startswith(b"%PDF-")
    pdf = PdfReader(paths["pdf"])
    assert len(pdf.pages) > 1
    assert "AI-assisted draft" in pdf.pages[0].extract_text()
    audit = json.loads(paths["json"].read_text())
    assert audit["package"]["citation_audit"]
    assert audit["package"]["demo_mode"]
    if language == Language.PERSIAN:
        with ZipFile(paths["docx"]) as doc:
            xml = doc.read("word/document.xml").decode()
            assert "w:bidi" in xml and "w:rtl" in xml
            assert brief.topic in xml
