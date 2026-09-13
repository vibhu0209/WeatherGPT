import pytest


@pytest.fixture(autouse=True)
def disable_live_llm_for_unit_tests(monkeypatch):
    """Unit tests must not spend live Groq quota or depend on network AI."""
    from app import ai, groq_client, groq_orchestrator, main

    monkeypatch.setattr(ai.gemini_polisher.settings, 'gemini_api_key', '', raising=False)
    monkeypatch.setattr(ai.gemini_polisher.settings, 'gemini_model', '', raising=False)
    monkeypatch.setattr(groq_client.groq_client.settings, 'groq_api_key', '', raising=False)
    monkeypatch.setattr(groq_client.groq_client.settings, 'groq_model', '', raising=False)
    monkeypatch.setattr(groq_orchestrator.groq_client.settings, 'groq_api_key', '', raising=False)
    monkeypatch.setattr(groq_orchestrator.groq_client.settings, 'groq_model', '', raising=False)
    monkeypatch.setattr(main.groq_client.settings, 'groq_api_key', '', raising=False)
    monkeypatch.setattr(main.groq_client.settings, 'groq_model', '', raising=False)
