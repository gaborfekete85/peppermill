"""Hermetic tests for AnthropicProvider using httpx.MockTransport — no network."""

import httpx
import pytest

from peppermill.providers.anthropic import AnthropicProvider

# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


def test_constructor_requires_api_key(monkeypatch):
    """No api_key arg and no env var → fail loudly at construction."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_constructor_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    provider = AnthropicProvider()
    assert provider.api_key == "env-key"


def test_constructor_explicit_api_key_overrides_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    provider = AnthropicProvider(api_key="explicit-key")
    assert provider.api_key == "explicit-key"


def test_constructor_defaults_to_haiku_4_5_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    provider = AnthropicProvider()
    assert provider.model == "claude-haiku-4-5-20251001"


def test_constructor_accepts_model_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    provider = AnthropicProvider(model="claude-sonnet-4-6")
    assert provider.model == "claude-sonnet-4-6"


def test_constructor_with_injected_client_does_not_create_its_own():
    """When a client is supplied, the provider stores it as-is."""
    sentinel_client = httpx.AsyncClient()
    provider = AnthropicProvider(api_key="x", client=sentinel_client)
    assert provider._client is sentinel_client
