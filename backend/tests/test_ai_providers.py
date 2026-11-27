"""The AI client speaks to Anthropic and to OpenAI-style providers (OpenAI, Azure OpenAI, Gemini, self-hosted)."""
import json

import httpx
import pytest

from app.config import get_settings
from app.services import ai

IMAGE = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}}
PDF = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "JVBERg=="}}


@pytest.fixture
def provider(monkeypatch):
    """Configure a provider through the environment and capture the request sent to it."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        if "/v1/messages" in seen["url"]:
            return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}],
                                             "usage": {"input_tokens": 5, "output_tokens": 2}})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}],
                                         "usage": {"prompt_tokens": 7, "completion_tokens": 3}})

    def use(**env):
        for k in ("AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return seen

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    yield use
    get_settings.cache_clear()


def test_anthropic_default_and_legacy_key(provider):
    seen = provider(ANTHROPIC_API_KEY="legacy")
    assert get_settings().ai_configured and get_settings().ai_model_name == "claude-sonnet-5-5"
    assert ai.complete("sys", [{"type": "text", "text": "q"}, IMAGE, PDF]) == ("hi", 5, 2)
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "legacy"
    assert seen["body"]["system"] == "sys" and seen["body"]["messages"][0]["content"][2] == PDF
    assert ai.supports_pdf()


def test_openai_translates_blocks(provider):
    seen = provider(AI_PROVIDER="openai", AI_API_KEY="sk-test", AI_MODEL="some-model")
    assert ai.complete("sys", [{"type": "text", "text": "q"}, IMAGE, PDF], 500) == ("hi", 7, 3)
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer sk-test"
    body = seen["body"]
    assert body["model"] == "some-model" and body["max_completion_tokens"] == 500 and "max_tokens" not in body
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    parts = body["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "q"}
    assert parts[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}
    assert parts[2]["type"] == "file" and parts[2]["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_azure_openai_uses_deployment_and_api_key_header(provider):
    seen = provider(AI_PROVIDER="azure_openai", AI_API_KEY="az", AI_MODEL="compliance-gpt",
                    AI_BASE_URL="https://acme.openai.azure.com/")
    ai.complete("sys", "plain text")
    assert seen["url"] == ("https://acme.openai.azure.com/openai/deployments/compliance-gpt/chat/completions"
                           "?api-version=2024-10-21")
    assert seen["headers"]["api-key"] == "az" and "authorization" not in seen["headers"]
    assert seen["body"]["messages"][1]["content"] == "plain text"


def test_gemini_and_self_hosted(provider):
    seen = provider(AI_PROVIDER="gemini", AI_API_KEY="g", AI_MODEL="gemini-model")
    ai.complete("sys", "q", 300)
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert seen["body"]["max_tokens"] == 300 and not ai.supports_pdf()

    # A local server needs no key
    seen = provider(AI_PROVIDER="openai_compatible", AI_MODEL="llama3.1", AI_BASE_URL="http://ollama:11434/v1")
    assert get_settings().ai_configured
    ai.complete("sys", "q")
    assert seen["url"] == "http://ollama:11434/v1/chat/completions" and "authorization" not in seen["headers"]


def test_incomplete_configuration_is_not_available(provider):
    provider(AI_PROVIDER="openai", AI_API_KEY="sk")  # no model
    assert not get_settings().ai_configured
    with pytest.raises(ai.AiError):
        ai.complete("sys", "q")
    provider(AI_PROVIDER="openai_compatible", AI_MODEL="m")  # no URL
    assert not get_settings().ai_configured
    provider(AI_PROVIDER="unknown", AI_API_KEY="k", AI_MODEL="m", AI_BASE_URL="https://x")
    assert not get_settings().ai_configured


def test_status_reports_provider(owner, provider):
    provider(AI_PROVIDER="openai_compatible", AI_MODEL="llama3.1", AI_BASE_URL="http://ollama:11434/v1")
    st = owner.get("/api/ai/status").json()
    assert st["available"] is True and st["provider"] == "openai_compatible" and st["model"] == "llama3.1"
    assert owner.put("/api/org/ai", json={"enabled": True, "acknowledge_data_sharing": True}).status_code == 200


def test_evidence_pdf_sent_as_text_when_provider_cannot_read_pdfs(provider):
    from types import SimpleNamespace

    from app.services import evidence_ai

    ev = SimpleNamespace(file_name="policy.pdf", title="Policy", kind="file", description="", url=None)
    pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
           b"trailer<</Root 1 0 R>>\n%%EOF")
    provider(ANTHROPIC_API_KEY="k")
    assert evidence_ai._content(ev, pdf)[1] == "pdf"
    provider(AI_PROVIDER="gemini", AI_API_KEY="g", AI_MODEL="m")
    try:
        assert evidence_ai._content(ev, pdf)[1] == "text"
    except ai.AiError:
        pass  # no extractable text in this minimal PDF: it is never sent as a document
