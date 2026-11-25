import json

import pytest
from fastapi.testclient import TestClient

from fristy.api.app import create_app
from fristy.integrations.remote import RemoteServer

H = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(svc):
    app = create_app(svc.config, svc)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def test_auth_required(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/status", headers=H).status_code == 200


def test_host_guard_blocks_dns_rebinding(client):
    r = client.get("/api/status", headers={**H, "Host": "evil.example.com"})
    assert r.status_code == 421


def test_ws_requires_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=bad") as ws:
            ws.receive_json()
    with client.websocket_connect("/ws?token=test-token") as ws:
        assert ws.receive_json()["type"] == "hello"


def test_settings_roundtrip_and_validation(client):
    r = client.patch("/api/settings", headers=H, json={"ui": {"language": "he", "accent_color": "#22d3ee"}})
    assert r.status_code == 200 and r.json()["ui"]["language"] == "he"
    assert client.patch("/api/settings", headers=H, json={"ui": {"accent_color": "red"}}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"approved_dirs": ["relative/path"]}).status_code == 422


def test_permission_change_audited(client, svc):
    client.patch("/api/settings", headers=H, json={"permissions": {"screen_view": True}})
    events = [e["event"] for e in client.get("/api/audit", headers=H).json()]
    assert "permissions.changed" in events


def test_secrets_api(client):
    assert client.put("/api/secrets/openai_api_key", headers=H, json={"value": "sk-abc"}).status_code == 200
    s = client.get("/api/secrets", headers=H).json()
    assert s["secrets"]["openai_api_key"] is True and "sk-abc" not in json.dumps(s)
    assert client.put("/api/secrets/root_password", headers=H, json={"value": "x"}).status_code == 404


def test_action_via_api_and_confirmation_list(client, svc):
    r = client.post("/api/actions/set_volume", headers=H, json={"args": {"level": 70}})
    assert r.json()["ok"] and svc.platform.volume == 70
    assert client.get("/api/confirmations", headers=H).json() == []


def test_memory_crud(client):
    m = client.post("/api/memory", headers=H, json={"category": "project", "key": "main", "value": "FRISTY"}).json()
    client.patch(f"/api/memory/{m['id']}", headers=H, json={"value": "FRISTY AI"})
    assert client.get("/api/memory", headers=H).json()[0]["value"] == "FRISTY AI"
    r = client.post("/api/memory", headers=H, json={"category": "fact", "key": "pin", "value": "my pin is 4455"})
    assert r.status_code == 400 and r.json()["code"] == "sensitive_data"
    exp = client.get("/api/memory-export", headers=H).json()
    assert exp["format"] == "fristy-memory-v1"
    client.delete("/api/memory", headers=H)
    assert client.get("/api/memory", headers=H).json() == []


def test_automation_api(client):
    r = client.post("/api/automations", headers=H, json={"name": "Q", "trigger": {"type": "manual"},
                                                         "confirmation": "none",
                                                         "steps": [{"action": "set_volume", "args": {"level": 5}}]})
    assert r.status_code == 200
    aid = r.json()["id"]
    assert client.post(f"/api/automations/{aid}/run", headers=H).json()["ok"]
    bad = client.post("/api/automations", headers=H, json={"name": "B", "steps": [{"action": "nope"}]})
    assert bad.status_code == 400
    assert len(client.get("/api/automation-templates", headers=H).json()) == 3


def test_emergency_stop_endpoint(client):
    assert client.post("/api/emergency-stop", headers=H).json()["ok"]


def test_voice_transcribe_silence(client):
    import numpy as np
    from fristy.voice_engine.audio import float32_to_wav
    wav = float32_to_wav(np.zeros(16000, dtype=np.float32))
    r = client.post("/api/voice/transcribe", headers={**H, "Content-Type": "audio/wav"}, content=wav)
    assert r.status_code == 200 and r.json()["silent"] is True
    client.post("/api/voice/mic", headers=H, json={"enabled": False})
    r = client.post("/api/voice/transcribe", headers=H, content=wav)
    assert r.status_code == 400 and r.json()["code"] == "mic_disabled"


def test_conversation_api(client, svc):
    c = svc.conversations.create("Test chat")
    svc.conversations.add_message(c["id"], "user", "hello world")
    assert client.get("/api/conversations?search=hello", headers=H).json()[0]["id"] == c["id"]
    assert len(client.get(f"/api/conversations/{c['id']}", headers=H).json()["messages"]) == 1
    client.delete(f"/api/conversations/{c['id']}", headers=H)
    assert client.get("/api/conversations", headers=H).json() == []


def test_remote_pairing_flow(svc):
    svc.settings.update({"remote": {"enabled": True}})
    remote = svc.remote
    with TestClient(remote.app) as rc:
        assert rc.get("/api/v1/status").status_code == 401
        assert rc.post("/api/v1/pair", json={"code": "123456", "device_name": "Phone"}).status_code == 403
        code = remote.start_pairing()["code"]
        wrong = "000000" if code != "000000" else "111111"
        assert rc.post("/api/v1/pair", json={"code": wrong, "device_name": "Phone"}).status_code == 403
        r = rc.post("/api/v1/pair", json={"code": code, "device_name": "Phone"})
        assert r.status_code == 200
        token = r.json()["token"]
        # code is single-use
        assert rc.post("/api/v1/pair", json={"code": code, "device_name": "X"}).status_code == 403
        st = rc.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})
        assert st.status_code == 200 and st.json()["device"] == "Phone"
        stored = svc.db.query("SELECT token_hash FROM remote_devices")[0]["token_hash"]
        assert token not in stored
        remote.revoke(remote.devices()[0]["id"])
        assert rc.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_remote_pairing_bruteforce_lockout(svc):
    svc.settings.update({"remote": {"enabled": True}})
    code = svc.remote.start_pairing()["code"]
    with TestClient(svc.remote.app) as rc:
        for _ in range(5):
            rc.post("/api/v1/pair", json={"code": "999999" if code != "999999" else "888888", "device_name": "A"})
        assert rc.post("/api/v1/pair", json={"code": code, "device_name": "A"}).status_code in (403, 429)


def test_remote_disabled(svc):
    with TestClient(svc.remote.app) as rc:
        assert rc.post("/api/v1/pair", json={"code": "123456", "device_name": "A"}).status_code == 503
