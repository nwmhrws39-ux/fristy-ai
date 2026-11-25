"""Wire-format tests for every provider using httpx.MockTransport (no network)."""
import json

import httpx
import pytest

from fristy.ai_engine.providers.anthropic import AnthropicProvider
from fristy.ai_engine.providers.gemini import GeminiProvider
from fristy.ai_engine.providers.ollama import OllamaProvider
from fristy.ai_engine.providers.openai_compat import OpenAICompatProvider
from fristy.ai_engine.types import Message, ProviderError, ToolCall, ToolDef

TOOLS = [ToolDef("set_volume", "Set volume", {"type": "object", "properties": {"level": {"type": "integer"}},
                                              "required": ["level"]})]


@pytest.fixture
def mock_http(monkeypatch):
    state = {"handler": None, "requests": []}
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *a, **kw):
            kw.pop("trust_env", None)
            def handler(request):
                state["requests"].append(request)
                return state["handler"](request)
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    return state


def sse(events):
    out = ""
    for e in events:
        if isinstance(e, tuple):
            out += f"event: {e[0]}\ndata: {json.dumps(e[1])}\n\n"
        else:
            out += f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n"
    return out.encode()


async def collect(gen):
    return [e async for e in gen]


async def test_ollama_stream_text_and_tools(mock_http):
    def handler(req):
        if req.url.path == "/api/chat":
            body = json.loads(req.content)
            assert body["tools"][0]["function"]["name"] == "set_volume"
            assert body["messages"][1]["images"] == ["iVBORimg"]
            lines = [{"message": {"role": "assistant", "content": "Setting "}, "done": False},
                     {"message": {"role": "assistant", "content": "", "tool_calls": [
                         {"function": {"name": "set_volume", "arguments": {"level": 30}}}]}, "done": False},
                     {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop",
                      "prompt_eval_count": 10, "eval_count": 5}]
            return httpx.Response(200, content="\n".join(json.dumps(l) for l in lines).encode())
        return httpx.Response(404)
    mock_http["handler"] = handler
    p = OllamaProvider("http://127.0.0.1:11434")
    evs = await collect(p.stream_chat("llama3.1", [Message("system", "s"), Message("user", "hi", images=["iVBORimg"])],
                                      TOOLS))
    assert [e.kind for e in evs] == ["text", "tool_call", "done"]
    assert evs[1].tool_call.arguments == {"level": 30}
    assert evs[2].usage["output_tokens"] == 5


async def test_ollama_discovery_capabilities(mock_http):
    def handler(req):
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llava:7b", "size": 4_000_000_000},
                                                        {"name": "nomic-embed-text", "size": 1},
                                                        {"name": "qwen3:8b", "size": 5_000_000_000}]})
        name = json.loads(req.content)["model"]
        caps = {"llava:7b": ["completion", "vision"], "nomic-embed-text": ["embedding"],
                "qwen3:8b": ["completion", "tools"]}[name]
        return httpx.Response(200, json={"capabilities": caps})
    mock_http["handler"] = handler
    models = await OllamaProvider("http://127.0.0.1:11434").list_models()
    by = {m.id: m for m in models}
    assert set(by) == {"llava:7b", "qwen3:8b"}
    assert by["llava:7b"].supports_vision and not by["llava:7b"].supports_tools
    assert by["qwen3:8b"].supports_tools and by["qwen3:8b"].local


async def test_ollama_unreachable(mock_http):
    def handler(req):
        raise httpx.ConnectError("refused")
    mock_http["handler"] = handler
    with pytest.raises(ProviderError) as e:
        await OllamaProvider("http://127.0.0.1:11434").list_models()
    assert "Is Ollama installed and running" in str(e.value)


async def test_openai_streaming_tool_call_fragments(mock_http):
    def handler(req):
        body = json.loads(req.content)
        assert req.headers["authorization"] == "Bearer sk-test"
        assert body["max_completion_tokens"] == 2048
        msgs = body["messages"]
        assert msgs[2]["tool_calls"][0]["function"]["arguments"] == '{"level": 10}'
        assert msgs[3] == {"role": "tool", "tool_call_id": "call_1", "content": "ok"}
        return httpx.Response(200, content=sse([
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_9", "function": {"name": "set_vol", "arguments": "{\"le"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "ume", "arguments": "vel\": 30}"}}]}}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
            "[DONE]",
        ]))
    mock_http["handler"] = handler
    p = OpenAICompatProvider("https://api.openai.com/v1", "sk-test")
    history = [Message("system", "s"), Message("user", "u"),
               Message("assistant", "", tool_calls=[ToolCall("set_volume", {"level": 10}, id="call_1")]),
               Message("tool", "ok", tool_call_id="call_1", name="set_volume")]
    evs = await collect(p.stream_chat("gpt-4o-mini", history, TOOLS))
    tc = [e for e in evs if e.kind == "tool_call"][0].tool_call
    assert (tc.name, tc.arguments, tc.id) == ("set_volume", {"level": 30}, "call_9")
    assert evs[-1].stop_reason == "tool_calls" and evs[-1].usage["input_tokens"] == 3


async def test_openai_retries_without_temperature(mock_http):
    calls = []
    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'temperature'"}})
        return httpx.Response(200, content=sse([{"choices": [{"delta": {"content": "ok"}}]}, "[DONE]"]))
    mock_http["handler"] = handler
    p = OpenAICompatProvider("http://127.0.0.1:1234/v1", None, "custom")
    evs = await collect(p.stream_chat("local-model", [Message("user", "u")]))
    assert evs[0].text == "ok" and len(calls) == 2 and "max_tokens" in calls[0]


async def test_openai_missing_key_and_401(mock_http):
    with pytest.raises(ProviderError):
        await collect(OpenAICompatProvider("https://api.openai.com/v1", None).stream_chat("gpt-4o", []))
    mock_http["handler"] = lambda r: httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
    with pytest.raises(ProviderError) as e:
        await OpenAICompatProvider("https://api.openai.com/v1", "bad").list_models()
    assert "invalid or missing API key" in str(e.value)


async def test_anthropic_stream(mock_http):
    def handler(req):
        assert req.headers["x-api-key"] == "k" and req.headers["anthropic-version"] == "2023-06-01"
        body = json.loads(req.content)
        assert body["system"] == "sys"
        assert body["tools"][0]["input_schema"]["required"] == ["level"]
        # tool result merged into a user turn with image
        tr = body["messages"][2]["content"][0]
        assert tr["type"] == "tool_result" and tr["content"][1]["type"] == "image"
        return httpx.Response(200, content=sse([
            ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 12}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "On it"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "set_volume"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"level\":"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": " 30}"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 1}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 20}}),
            ("message_stop", {"type": "message_stop"}),
        ]))
    mock_http["handler"] = handler
    p = AnthropicProvider("https://api.anthropic.com", "k")
    hist = [Message("system", "sys"), Message("user", "look"),
            Message("assistant", "", tool_calls=[ToolCall("analyze_screen", {}, id="toolu_0")]),
            Message("tool", '{"ok": true}', images=["/9j/jpeg"], tool_call_id="toolu_0", name="analyze_screen")]
    evs = await collect(p.stream_chat("claude-sonnet-5-5", hist, TOOLS))
    assert evs[0].text == "On it"
    tc = evs[1].tool_call
    assert (tc.id, tc.arguments) == ("toolu_1", {"level": 30})
    assert evs[-1].stop_reason == "tool_use" and evs[-1].usage == {"input_tokens": 12, "output_tokens": 20}


async def test_anthropic_error_event(mock_http):
    mock_http["handler"] = lambda r: httpx.Response(200, content=sse([
        ("error", {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})]))
    with pytest.raises(ProviderError) as e:
        await collect(AnthropicProvider("https://api.anthropic.com", "k").stream_chat("m", [Message("user", "x")]))
    assert e.value.retryable


async def test_gemini_stream_with_thought_signature(mock_http):
    def handler(req):
        assert req.headers["x-goog-api-key"] == "g"
        assert req.url.params["alt"] == "sse"
        body = json.loads(req.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "sys"
        model_turn = body["contents"][1]
        assert model_turn["role"] == "model"
        assert model_turn["parts"][0]["thoughtSignature"] == "sig0"
        assert body["contents"][2]["parts"][0]["functionResponse"]["response"] == {"ok": True}
        return httpx.Response(200, content=sse([
            {"candidates": [{"content": {"parts": [{"text": "Done thinking"}]}}]},
            {"candidates": [{"content": {"parts": [{"functionCall": {"name": "set_volume", "args": {"level": 30}},
                                                    "thoughtSignature": "sig1"}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 9}},
        ]))
    mock_http["handler"] = handler
    hist = [Message("system", "sys"), Message("user", "u"),
            Message("assistant", "", tool_calls=[ToolCall("get_volume", {}, extra={"thoughtSignature": "sig0"})]),
            Message("tool", '{"ok": true}', name="get_volume")]
    evs = await collect(GeminiProvider("https://generativelanguage.googleapis.com", "g").stream_chat("gemini-2.0-flash", hist, TOOLS))
    tc = evs[1].tool_call
    assert tc.arguments == {"level": 30} and tc.extra["thoughtSignature"] == "sig1"
    assert evs[-1].usage["output_tokens"] == 9


async def test_gemini_models_filter(mock_http):
    mock_http["handler"] = lambda r: httpx.Response(200, json={"models": [
        {"name": "models/gemini-2.0-flash", "displayName": "Gemini 2.0 Flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]})
    models = await GeminiProvider("https://generativelanguage.googleapis.com", "g").list_models()
    assert [m.id for m in models] == ["gemini-2.0-flash"]


async def test_manager_text_protocol_fallback(svc, mock_http):
    """A model without native tools still gets tools through the <action> protocol."""
    def handler(req):
        if req.url.path == "/api/chat":
            body = json.loads(req.content)
            assert "tools" not in body and "<action>" in body["messages"][0]["content"]
            lines = [{"message": {"content": "OK. "}, "done": False},
                     {"message": {"content": '<action>{"name": "set_volume", "arguments": {"level": 25}}</action>'}, "done": False},
                     {"message": {"content": ""}, "done": True}]
            return httpx.Response(200, content="\n".join(json.dumps(l) for l in lines).encode())
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "tinyllama", "size": 1}]})
        return httpx.Response(200, json={"capabilities": ["completion"]})
    mock_http["handler"] = handler
    await svc.ai.discover("ollama")
    assert svc.ai.active_model() == "tinyllama"
    evs = [e async for e in svc.ai.stream([Message("system", "s"), Message("user", "volume 25 please")], TOOLS)]
    texts = "".join(e.text for e in evs if e.kind == "text")
    calls = [e.tool_call for e in evs if e.kind == "tool_call"]
    assert texts.strip() == "OK." and calls[0].arguments == {"level": 25}


async def test_manager_retries_transient(svc, mock_http):
    n = {"c": 0}
    def handler(req):
        n["c"] += 1
        if n["c"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, content=json.dumps({"message": {"content": "hi"}, "done": True}).encode())
    mock_http["handler"] = handler
    svc.settings.update({"ai": {"model": "m"}})
    import fristy.ai_engine.manager as mgr
    orig = mgr.asyncio.sleep
    async def fast(_):
        return None
    mgr.asyncio.sleep = fast
    try:
        assert await svc.ai.complete([Message("user", "x")]) == "hi"
    finally:
        mgr.asyncio.sleep = orig
    assert n["c"] == 2


def test_cloud_flags(svc):
    assert not svc.ai.is_cloud("ollama") and svc.ai.is_cloud("anthropic")
    svc.settings.update({"ai": {"providers": {"custom": {"base_url": "http://localhost:1234/v1"}}}})
    assert not svc.ai.is_cloud("custom")
    svc.settings.update({"ai": {"providers": {"custom": {"base_url": "https://openrouter.ai/api/v1"}}}})
    assert svc.ai.is_cloud("custom")
