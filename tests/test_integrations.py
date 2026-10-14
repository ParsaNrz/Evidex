from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from evidex import rendering
from evidex.gates import GateContext, source_gate
from evidex.integrations import (
    MAX_REDIRECTS,
    CrossrefRetriever,
    IntegrationError,
    OpenAIProvider,
    request_json,
)
from evidex.models import JobStatus, ResearchPlan, Stage, VerificationStatus
from evidex.providers import FakeLLM, LLMRequest, PromptRegistry
from evidex.rendering import DocumentRenderer
from evidex.runner import PipelineRunner
from evidex.runtime import IntegratedProvider


def llm_request(brief, stage=Stage.PLAN):
    return LLMRequest(
        "job",
        stage,
        stage.value,
        1,
        {"brief": brief.model_dump(mode="json")},
        "Address the previous gate",
        PromptRegistry().load(stage),
        "job:plan:1",
    )


def metadata(doi="10.1234/example"):
    return {
        "DOI": doi,
        "title": ["Social support and student wellbeing"],
        "author": [{"given": "Test", "family": "Researcher"}],
        "published": {"date-parts": [[date.today().year]]},
        "container-title": ["Contract test journal"],
        "type": "journal-article",
        "abstract": "<jats:p>Social support is associated with student wellbeing.</jats:p>",
    }


def test_openai_contract_includes_schema_feedback_template_and_usage(brief):
    output = FakeLLM()._plan({"brief": brief.model_dump(mode="json")})
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert request.headers["Idempotency-Key"] == "job:plan:1"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert '"ResearchPlan"' in body["messages"][0]["content"]
        user = json.loads(body["messages"][1]["content"])
        assert user["gate_feedback"] == "Address the previous gate"
        assert user["input"]["document_template"][0]["node_id"] == "title"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(output)}}],
                "usage": {"prompt_tokens": 300, "completion_tokens": 500},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OpenAIProvider("test-secret", client=client).complete_json(llm_request(brief))
    assert response.output == output
    assert response.input_tokens == 300 and response.output_tokens == 500
    assert len(requests) == 1


@pytest.mark.parametrize("content", ["not JSON", "[]", '{"unexpected":"field"}'])
def test_malformed_llm_output_rejected(brief, content):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        )
    ) as client:
        with pytest.raises(IntegrationError, match="schema-invalid"):
            OpenAIProvider("secret", client=client).complete_json(llm_request(brief))


def test_network_retries_are_bounded_and_errors_do_not_leak_secrets(monkeypatch):
    monkeypatch.setattr("evidex.integrations.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, text="secret-provider-response")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IntegrationError, match="HTTP 429 at example.test after retries"):
            request_json(client, "GET", "https://example.test")
        with pytest.raises(IntegrationError) as error:
            request_json(client, "GET", "https://example.test/v1?api_key=secret-token")
        assert "secret" not in str(error.value)
        assert "example.test" in str(error.value)
    assert len(calls) == 6


def test_auth_failure_is_not_retried(monkeypatch):
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: calls.append(r) or httpx.Response(401, json={"error": "secret"})
        )
    ) as client:
        with pytest.raises(IntegrationError, match="HTTP 401"):
            request_json(client, "GET", "https://example.test")
    assert len(calls) == 1


def test_llm_redirect_to_canonical_url_is_followed(brief):
    """Regression: a gateway 307 on the chat-completions path killed the plan stage.

    The endpoint answered "use /v1/chat/completions/ instead"; that is a URL detail, not a
    provider outage, so the request is replayed once and the stage still runs.
    """
    output = FakeLLM()._plan({"brief": brief.model_dump(mode="json")})
    seen = []

    def handler(request):
        seen.append(
            (
                request.method,
                str(request.url),
                request.headers.get("Authorization"),
                request.content,
            )
        )
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(307, headers={"Location": "/v1/chat/completions/"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OpenAIProvider(
            "test-secret", base_url="https://llm.example/v1", client=client
        ).complete_json(llm_request(brief))
    assert response.output == output
    assert [(method, url) for method, url, _, _ in seen] == [
        ("POST", "https://llm.example/v1/chat/completions"),
        ("POST", "https://llm.example/v1/chat/completions/"),
    ]
    # 307 preserves method and body; the origin is unchanged, so the key is replayed.
    assert seen[0][3] == seen[1][3] and seen[0][3]
    assert {auth for _, _, auth, _ in seen} == {"Bearer test-secret"}


def test_redirect_to_another_origin_is_refused_and_the_payload_is_not_resent(brief):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            307, headers={"Location": "https://elsewhere.example/v1/chat/completions"}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IntegrationError, match="redirects to elsewhere.example") as error:
            OpenAIProvider(
                "test-secret", base_url="https://llm.example/v1", client=client
            ).complete_json(llm_request(brief))
    assert "base URL" in str(error.value)
    assert seen == ["https://llm.example/v1/chat/completions"]  # Never followed, never retried.


def test_base_url_without_the_api_path_is_reported_as_a_configuration_error(brief):
    """A gateway site root instead of its API path redirects to its own login page.

    Evidex must not call that a provider outage, and must never POST the brief and the API
    key to a login form: the redirect is followed as a bodyless GET, the HTML answer is
    recognised, and the checkpoint names the base URL as the thing to fix.
    """
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url)))
        if request.url.path == "/chat/completions":
            return httpx.Response(302, headers={"Location": "/login?next=%2Fchat%2Fcompletions"})
        return httpx.Response(
            200, headers={"Content-Type": "text/html"}, text="<html>Sign in</html>"
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IntegrationError, match="HTML page") as error:
            OpenAIProvider(
                "thk_live_secret", base_url="https://gateway.example", client=client
            ).complete_json(llm_request(brief))
    assert "base URL" in str(error.value)
    assert "secret" not in str(error.value)
    assert seen == [
        ("POST", "https://gateway.example/chat/completions"),
        ("GET", "https://gateway.example/login?next=%2Fchat%2Fcompletions"),
    ]


def test_non_https_redirect_target_is_refused():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"Location": "http://llm.example/v1/"})
        )
    ) as client:
        with pytest.raises(IntegrationError, match="non-HTTPS"):
            request_json(client, "GET", "https://llm.example/v1/models")


def test_redirect_loop_is_bounded_and_names_the_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "/v1/chat/completions"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IntegrationError, match="at llm.example redirected more than 3 times"):
            request_json(
                client, "POST", "https://llm.example/v1/chat/completions", json={"prompt": "hi"}
            )
    assert len(calls) == MAX_REDIRECTS + 1


def test_crossref_never_invents_evidence_and_flags_retractions():
    record = CrossrefRetriever._record(metadata(), "10.1234/example")
    assert record.verification.status == VerificationStatus.VERIFIED
    assert record.notes[0].paraphrase == "Social support is associated with student wellbeing."
    assert "verbatim" in record.notes[0].locator
    assert record.verification.checked_at is not None
    assert CrossrefRetriever._record(metadata(), "different-doi") is None
    for missing in ["abstract", "author", "title", "published"]:
        item = metadata()
        del item[missing]
        assert CrossrefRetriever._record(item, "10.1234/example") is None
    item = metadata()
    item["update-to"] = [{"type": "retraction"}]
    assert CrossrefRetriever._record(item, item["DOI"]).retracted


def test_insufficient_crossref_results_fail_source_gate(brief, fake_artifacts):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"message": {"items": []}})
        )
    ) as client:
        registry = CrossrefRetriever(client=client).gather(
            brief, ResearchPlan.model_validate(fake_artifacts["plan"])
        )
    assert not registry.sources
    gate = source_gate(
        registry,
        GateContext(
            brief=brief,
            fixture_mode=False,
            plan=ResearchPlan.model_validate(fake_artifacts["plan"]),
        ),
    )
    assert not gate.passed


def test_mocked_live_pipeline_retrieves_real_shaped_records_and_renders(brief, store, tmp_path):
    fake = FakeLLM()  # Test response generator, never used as a production fallback.
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "api.crossref.org":
            if request.url.path == "/works":
                prefix = hashlib.sha256(
                    request.url.params["query.bibliographic"].encode()
                ).hexdigest()[:8]
                return httpx.Response(
                    200,
                    json={
                        "message": {"items": [{"DOI": f"10.1234/{prefix}-{i}"} for i in range(8)]}
                    },
                )
            doi = request.url.path.removeprefix("/works/")
            return httpx.Response(200, json={"message": metadata(doi)})
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])["input"]
        if "sections" in payload:
            result = fake._review(payload)
        elif "node" in payload:
            result = fake._section(payload)
        elif "registry" in payload:
            result = fake._outline(payload)
        else:
            result = fake._plan(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = IntegratedProvider(
        OpenAIProvider("secret", client=client),
        CrossrefRetriever(client=client),
        DocumentRenderer(tmp_path / "exports"),
    )
    runner = PipelineRunner(store, provider)
    job = runner.create_project(brief)
    for expected in [Stage.PLAN, Stage.SOURCES, Stage.OUTLINE]:
        state = runner.run(job.job_id)
        assert state.status == JobStatus.AWAITING_APPROVAL, state.feedback_for_retry
        assert state.pending_approval == expected
        runner.approve(job.job_id, expected)
    state = runner.run(job.job_id)
    assert state.status == JobStatus.COMPLETED, state.feedback_for_retry
    package = store.get_artifact(job.job_id, Stage.OUTPUT, "output")
    assert package["demo_mode"] is False
    assert package["ai_use_disclosure"]
    assert {f["format"] for f in package["files"]} == {"docx", "pdf", "json"}
    assert all(Path(f["path"]).stat().st_size > 0 for f in package["files"])
    registry = store.get_artifact(job.job_id, Stage.SOURCES, "sources")
    assert len(registry["sources"]) == 15
    assert all(s["origin"] == "api" for s in registry["sources"])
    assert any(r.url.host == "api.crossref.org" for r in seen)
    provider.close()


def test_same_origin_redirect_does_not_stop_the_plan_stage(brief, store, tmp_path):
    """The reported failure: `plan could not run: External service HTTP 307`.

    A gateway that canonicalises the chat-completions URL is a configuration detail, so
    the plan stage must complete and reach its human checkpoint.
    """
    inner = _mocked_live_handler(FakeLLM())

    def handler(request):
        if request.url.host == "api.crossref.org":
            return inner(request)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(307, headers={"Location": "/v1/chat/completions/"})
        return inner(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = _mocked_live_provider(client, DocumentRenderer(tmp_path / "exports"))
    runner = PipelineRunner(store, provider)
    job = runner.create_project(brief)
    state = runner.run(job.job_id)
    assert state.status == JobStatus.AWAITING_APPROVAL, state.feedback_for_retry
    assert state.pending_approval == Stage.PLAN
    assert store.get_artifact(job.job_id, Stage.PLAN, "plan") is not None
    provider.close()


def test_cross_origin_redirect_reports_the_configuration_cause(brief, store, tmp_path):
    """A redirect off the configured origin is refused and explained, not retried."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://login.example/sso"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = IntegratedProvider(
        OpenAIProvider("secret", base_url="https://llm.example/v1", client=client),
        None,
        DocumentRenderer(tmp_path),
    )
    runner = PipelineRunner(store, provider)
    job = runner.create_project(brief)
    state = runner.run(job.job_id)
    assert state.status == JobStatus.NEEDS_HUMAN
    assert state.current_stage == Stage.PLAN
    feedback = state.feedback_for_retry or ""
    assert "could not run" in feedback
    assert "redirects to login.example" in feedback
    assert "base URL" in feedback
    # The model produced nothing, so the student is not asked to regenerate a stage.
    assert "regenerate" not in feedback
    # Each of the runner's three attempts makes exactly one request; the redirect itself
    # is never followed to another origin.
    assert seen == ["https://llm.example/v1/chat/completions"] * 3
    errors = [c for c in store.list_model_calls(job.job_id) if c.status == "provider_error"]
    assert len(errors) == 3
    assert all("secret" not in c.error for c in errors)
    assert store.get_artifact(job.job_id, Stage.PLAN, "plan") is None
    provider.close()


def test_provider_mode_cannot_change_on_resume(brief, store):
    runner = PipelineRunner(store, FakeLLM())
    job = runner.create_project(brief)
    runner.provider.fixture_mode = False
    with pytest.raises(ValueError, match="mode mismatch"):
        runner.run(job.job_id)


def test_live_results_never_generate_student_data(brief, tmp_path):
    from evidex.models import DataSituation, OutlineNode
    from evidex.providers import Prompt

    class NeverCalled:
        fixture_mode = False
        name = "test"
        model = "test"

        def complete_json(self, request):
            raise AssertionError("Findings must not be sent to the LLM without a dataset")

    brief.data_situation = DataSituation.HAS_DATA
    node = OutlineNode(
        node_id="results",
        title="Chapter 4: Results/Findings",
        purpose="Report actual data",
        word_budget=1000,
    )
    request = LLMRequest(
        "job",
        Stage.WRITE,
        "results",
        1,
        {"brief": brief.model_dump(mode="json"), "node": node.model_dump()},
        None,
        Prompt("write", "1", ""),
        "job:write:1",
    )
    response = IntegratedProvider(NeverCalled(), None, DocumentRenderer(tmp_path)).complete_json(
        request
    )
    assert response.output["body"].startswith("[STUDENT_DATA:")
    assert response.output["claims"] == []


def test_live_provider_failure_exhausts_attempts_without_fake_fallback(
    brief, store, tmp_path, monkeypatch
):
    monkeypatch.setattr("evidex.integrations.time.sleep", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401)))
    provider = IntegratedProvider(
        OpenAIProvider("secret", client=client), None, DocumentRenderer(tmp_path)
    )
    runner = PipelineRunner(store, provider)
    job = runner.create_project(brief)
    state = runner.run(job.job_id)
    assert state.status == JobStatus.NEEDS_HUMAN
    assert state.current_stage == Stage.PLAN
    errors = [c for c in store.list_model_calls(job.job_id) if c.status == "provider_error"]
    assert len(errors) == 3
    assert all(c.provider == "openai-compatible" and "secret" not in c.error for c in errors)
    assert store.get_artifact(job.job_id, Stage.SOURCES, "sources") is None
    provider.close()


def _mocked_live_provider(client, renderer):
    return IntegratedProvider(
        OpenAIProvider("secret", client=client),
        CrossrefRetriever(client=client),
        renderer,
    )


def _mocked_live_handler(fake, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        if request.url.host == "api.crossref.org":
            if request.url.path == "/works":
                prefix = hashlib.sha256(
                    request.url.params["query.bibliographic"].encode()
                ).hexdigest()[:8]
                return httpx.Response(
                    200,
                    json={
                        "message": {"items": [{"DOI": f"10.1234/{prefix}-{i}"} for i in range(8)]}
                    },
                )
            doi = request.url.path.removeprefix("/works/")
            return httpx.Response(200, json={"message": metadata(doi)})
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])["input"]
        if "sections" in payload:
            result = fake._review(payload)
        elif "node" in payload:
            result = fake._section(payload)
        elif "registry" in payload:
            result = fake._outline(payload)
        else:
            result = fake._plan(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    return handler


def test_render_failure_reports_the_cause_instead_of_an_export_schema_error(
    brief, store, tmp_path
):
    """Regression: a failing renderer was reported as `ExportPackage` schema errors.

    Rendering is application code, so an empty payload was mistaken for model output and
    the student was told to regenerate a stage no model had produced.
    """
    client = httpx.Client(transport=httpx.MockTransport(_mocked_live_handler(FakeLLM())))
    missing = tmp_path / "no-such-font.ttf"
    provider = _mocked_live_provider(client, DocumentRenderer(tmp_path / "exports", missing))
    runner = PipelineRunner(store, provider)
    job = runner.create_project(brief)
    for expected in [Stage.PLAN, Stage.SOURCES, Stage.OUTLINE]:
        state = runner.run(job.job_id)
        assert state.status == JobStatus.AWAITING_APPROVAL, state.feedback_for_retry
        runner.approve(job.job_id, expected)
    state = runner.run(job.job_id)

    assert state.status == JobStatus.NEEDS_HUMAN
    assert state.current_stage == Stage.OUTPUT
    feedback = state.feedback_for_retry or ""
    assert str(missing) in feedback and "EVIDEX_PDF_FONT" in feedback
    assert "could not run" in feedback
    # The old behaviour: an empty payload validated as model output, blaming the student.
    assert "validation error" not in feedback
    assert "regenerate only this stage" not in feedback

    attempts = [item for item in store.list_attempts(job.job_id) if item["stage"] == "output"]
    assert all(item["status"] == "provider_error" for item in attempts)
    assert all(str(missing) in (item["error"] or "") for item in attempts)
    assert all(item["output"] is None for item in attempts)
    assert store.get_artifact(job.job_id, Stage.OUTPUT, "output") is None
    gate = store.get_gate_result(job.job_id, Stage.OUTPUT, "output", 1)
    assert gate is not None and not gate.passed
    assert [check.check_id for check in gate.checks] == ["stage_executed"]
    with pytest.raises(ValueError, match="cannot be overridden"):
        runner.override_failed_checks(
            job.job_id, ["stage_executed"], "Renderer was broken; ignore it.", actor="student"
        )
    provider.close()


def test_configured_font_is_never_second_guessed(tmp_path, monkeypatch):
    configured = tmp_path / "chosen.ttf"
    renderer = DocumentRenderer(tmp_path / "exports", configured)
    with pytest.raises(ValueError, match="chosen.ttf"):
        renderer.pdf_font()
    configured.write_bytes(b"placeholder")  # Existence is checked here; fpdf validates content.
    monkeypatch.setattr(rendering, "PDF_FONT_CANDIDATES", ())
    assert renderer.pdf_font() == configured


def test_font_is_discovered_only_when_no_path_is_configured(tmp_path, monkeypatch):
    renderer = DocumentRenderer(tmp_path / "exports")
    assert renderer.pdf_font().is_file()
    monkeypatch.setattr(rendering, "PDF_FONT_CANDIDATES", (str(tmp_path / "absent.ttf"),))
    with pytest.raises(ValueError, match="EVIDEX_PDF_FONT"):
        renderer.pdf_font()
