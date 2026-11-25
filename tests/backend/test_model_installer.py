import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from fristy.ai_engine.models_catalog import recommend
from fristy.api.app import create_app


@pytest.fixture
def ollama(monkeypatch):
    state = {"models": ["llama3.2:3b"], "pulled": [], "fail": False, "slow": False}
    real = httpx.AsyncClient

    def handler(req):
        p = req.url.path
        if p == "/api/version":
            return httpx.Response(200, json={"version": "0.9.0"})
        if p == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m, "size": 2_000_000_000} for m in state["models"]]})
        if p == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion", "tools"]})
        if p == "/api/pull":
            name = json.loads(req.content)["model"]
            if state["fail"]:
                return httpx.Response(200, content=b'{"status":"pulling manifest"}\n{"error":"pull model manifest: file does not exist"}\n')
            lines = [{"status": "pulling manifest"}]
            for done in (0, 500, 1000):
                lines.append({"status": "pulling abc", "digest": "sha256:abc", "total": 1000, "completed": done})
            lines.append({"status": "pulling def", "digest": "sha256:def", "total": 10, "completed": 10})
            lines.append({"status": "success"})
            state["pulled"].append(name)
            state["models"].append(name)
            return httpx.Response(200, content="\n".join(json.dumps(l) for l in lines).encode())
        if p == "/api/delete":
            name = json.loads(req.content)["model"]
            if name not in state["models"]:
                return httpx.Response(404, json={"error": f"model '{name}' not found"})
            state["models"].remove(name)
            return httpx.Response(200)
        return httpx.Response(404)

    class P(real):
        def __init__(self, *a, **kw):
            kw.pop("trust_env", None)
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", P)
    return state


def test_recommendations_by_ram():
    assert recommend(32)["main"] == "qwen2.5:7b" and recommend(32)["vision"] == "gemma3:4b"
    assert recommend(8)["main"] == "qwen2.5:3b"
    r = recommend(4)
    assert r["main"] == "qwen2.5:1.5b" and r["vision"] is None
    assert not next(m for m in r["models"] if m["id"] == "qwen2.5:7b")["fits"]


async def wait_job(svc, model):
    for _ in range(200):
        j = svc.models.jobs.get(model)
        if j and j["status"] != "downloading":
            return j
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


async def test_pull_progress_and_auto_select(svc, ollama):
    await svc.ai.discover("ollama")
    svc.settings.update({"ai": {"provider": "ollama", "model": ""}})
    q = svc.bus.subscribe()
    svc.models.start("qwen2.5:7b")
    job = await wait_job(svc, "qwen2.5:7b")
    assert job["status"] == "done" and job["percent"] == 100.0 and job["total"] == 1010
    assert svc.settings.current.ai.model == "qwen2.5:7b"  # auto-selected
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert any(e["type"] == "ai.pull" and e["status"] == "done" for e in events)
    st = await svc.models.status()
    assert st["ollama_running"] and "qwen2.5:7b" in st["installed"]
    assert next(m for m in st["models"] if m["id"] == "qwen2.5:7b")["installed"]


async def test_vision_model_not_auto_selected(svc, ollama):
    svc.settings.update({"ai": {"provider": "ollama", "model": ""}})
    svc.models.start("gemma3:4b")
    await wait_job(svc, "gemma3:4b")
    assert svc.settings.current.ai.model == ""


async def test_existing_selection_kept(svc, ollama):
    await svc.ai.discover("ollama")
    svc.settings.update({"ai": {"provider": "ollama", "model": "llama3.2:3b"}})
    svc.models.start("qwen2.5:3b")
    await wait_job(svc, "qwen2.5:3b")
    assert svc.settings.current.ai.model == "llama3.2:3b"


async def test_pull_error_reported(svc, ollama):
    ollama["fail"] = True
    svc.models.start("nonexistent-model:1b")
    job = await wait_job(svc, "nonexistent-model:1b")
    assert job["status"] == "error" and "does not exist" in job["error"]


def test_invalid_names_rejected(svc):
    from fristy.computer_control.base import ActionError
    for bad in ["", "../../etc", "a b", "model;rm -rf"]:
        with pytest.raises(ActionError):
            svc.models.start(bad)


async def test_delete_clears_selection(svc, ollama):
    await svc.ai.discover("ollama")
    svc.settings.update({"ai": {"provider": "ollama", "model": "llama3.2:3b"}})
    await svc.models.delete("llama3.2:3b")
    assert svc.settings.current.ai.model == "" and "llama3.2:3b" not in ollama["models"]


def test_api_routes(svc, ollama):
    app = create_app(svc.config, svc)
    H = {"Authorization": "Bearer test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        st = c.get("/api/ai/local-models", headers=H).json()
        assert st["ollama_running"] and st["main"]
        assert c.post("/api/ai/local-models/pull", headers=H, json={"model": "bad name"}).status_code == 400
        r = c.post("/api/ai/local-models/delete", headers=H, json={"model": "missing:1b"})
        assert r.status_code == 400 and "not found" in r.json()["detail"]
        assert c.get("/api/ai/local-models").status_code == 401
