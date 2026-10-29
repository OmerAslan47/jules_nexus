import pytest
import os
import sys
import tempfile
import json
import time

# Ensure imports work without needing external `core` package installed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from brain_router import EndpointCircuitBreaker, ResponseCache, ConversationBuffer, BrainRouter


def test_endpoint_circuit_breaker():
    cb = EndpointCircuitBreaker(name="Test_Endpoint", failure_threshold=2, cooldown_sec=0.1)
    assert cb.can_attempt() is True
    assert cb.state == EndpointCircuitBreaker.STATE_CLOSED

    cb.record_failure("Error 1")
    assert cb.can_attempt() is True
    assert cb.state == EndpointCircuitBreaker.STATE_CLOSED

    cb.record_failure("Error 2")
    assert cb.state == EndpointCircuitBreaker.STATE_OPEN
    assert cb.can_attempt() is False

    time.sleep(0.15)
    assert cb.can_attempt() is True
    assert cb.state == EndpointCircuitBreaker.STATE_HALF_OPEN

    cb.record_success(15.0)
    assert cb.state == EndpointCircuitBreaker.STATE_CLOSED
    metrics = cb.get_metrics()
    assert metrics["total_requests"] == 3
    assert metrics["total_successes"] == 1


def test_response_cache():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        cache_path = tmp.name

    try:
        cache = ResponseCache(cache_path=cache_path, max_entries=5, ttl_sec=100)
        assert cache.get("hello", "sys") is None

        cache.put("hello", "sys", "world", "test_source")
        res = cache.get("hello", "sys")
        assert res is not None
        assert res["response"] == "world"
        assert "test_source" in res["source"]

        # Do not cache tool calls
        cache.put("tool_test", "sys", "TOOL_CALL: do_something", "test_source")
        assert cache.get("tool_test", "sys") is None
    finally:
        if os.path.exists(cache_path):
            os.remove(cache_path)


def test_conversation_buffer():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        hist_path = tmp.name

    try:
        buf = ConversationBuffer(max_turns=3, history_path=hist_path)
        buf.add_exchange("Merhaba", "Selam, nasıl yardımcı olabilirim?")
        buf.add_exchange("Nasılsın?", "Harikayım!")

        msgs = buf.get_formatted_messages(limit=5)
        assert len(msgs) == 4
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Merhaba"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Selam, nasıl yardımcı olabilirim?"

        buf.clear()
        assert len(buf.get_formatted_messages()) == 0
    finally:
        if os.path.exists(hist_path):
            os.remove(hist_path)


def test_brain_router_ask_cached():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        cfg_path = tmp.name

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"colab_tunnel_url": ""}, f)

    try:
        router = BrainRouter(config_path=cfg_path)
        router.cache.put("test_q", "sys_p", "test_ans", "unit_test")
        res = router.ask("test_q", system_prompt="sys_p", use_cache=True)
        assert res["response"] == "test_ans"
        assert "unit_test" in res["source"]
    finally:
        if os.path.exists(cfg_path):
            os.remove(cfg_path)
