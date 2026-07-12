"""Tests for GeminiClient health-check caching (hardening under parallel /health)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quizzer.generation import gemini_client as gc_module
from quizzer.generation.gemini_client import GeminiClient


@pytest.fixture()
def client_with_fake_backend():
    client = GeminiClient(api_key="dummy-not-used")
    client._client = MagicMock()
    return client


def test_health_check_is_cached_within_ttl(client_with_fake_backend, monkeypatch):
    client = client_with_fake_backend
    calls = {"n": 0}

    def fake_list():
        calls["n"] += 1
        return iter([object()])

    client._client.models.list.side_effect = fake_list
    monkeypatch.setattr(gc_module.time, "monotonic", lambda: 1000.0)

    assert client.health_check() is True
    assert client.health_check() is True
    assert calls["n"] == 1  # second call served from cache


def test_health_check_refreshes_after_ttl(client_with_fake_backend, monkeypatch):
    client = client_with_fake_backend
    calls = {"n": 0}

    def fake_list():
        calls["n"] += 1
        return iter([object()])

    client._client.models.list.side_effect = fake_list

    now = {"t": 1000.0}
    monkeypatch.setattr(gc_module.time, "monotonic", lambda: now["t"])

    assert client.health_check() is True
    now["t"] += GeminiClient._HEALTH_TTL_S + 1  # advance past the TTL
    assert client.health_check() is True
    assert calls["n"] == 2  # re-checked after expiry


def test_health_check_reports_failure(client_with_fake_backend, monkeypatch):
    client = client_with_fake_backend
    client._client.models.list.side_effect = RuntimeError("network down")
    monkeypatch.setattr(gc_module.time, "monotonic", lambda: 1000.0)
    assert client.health_check() is False
