"""Scripted Ollama-compatible server for UI/integration testing WITHOUT a real model.

It implements /api/tags, /api/show and streaming /api/chat (NDJSON) exactly like
Ollama, but its "model" follows simple rules so end-to-end flows can be tested:

* agent planner prompt          -> returns a JSON plan built from keywords
* message mentions "system"/"ram"/"cpu"  -> calls the system_info tool
* message mentions "note"/"file" -> calls create_text_file in the first approved dir
* after a tool result           -> summarises the real result honestly
* anything else                 -> a short canned answer (streamed word by word)

Usage:  python tools/mock_ollama.py --port 11434
This is a TEST TOOL only; it is never shipped in the installer.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "fristy-mock:latest"
INSTALLED: list[str] = [MODEL]


def plan_for(text: str) -> dict:
    steps = []
    t = text.lower()
    if re.search(r"system|ram|cpu|מעבד|זיכרון", t):
        steps.append({"action": "system_info", "args": {}, "description": "Read system information"})
    if re.search(r"note|file|קובץ", t):
        steps.append({"action": "create_text_file", "args": {"path": "fristy-note.txt", "content": "Created by FRISTY agent mode."},
                      "description": "Create a note"})
    if re.search(r"discord", t):
        steps.append({"action": "launch_app", "args": {"name": "Discord"}, "description": "Open Discord"})
    if re.search(r"volume|עוצמה", t):
        m = re.search(r"(\d{1,3})", t)
        steps.append({"action": "set_volume", "args": {"level": int(m.group(1)) if m else 30}, "description": "Set volume"})
    return {"summary": "Plan for: " + text[:80], "steps": steps}


def respond(body: dict):
    msgs = body.get("messages", [])
    tools = {t["function"]["name"] for t in body.get("tools") or []}
    system = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
    last = msgs[-1] if msgs else {"role": "user", "content": ""}
    user_texts = [m["content"] for m in msgs if m["role"] == "user"]
    last_user = user_texts[-1] if user_texts else ""
    if "FRISTY's planner" in system:
        return json.dumps(plan_for(last_user)), []
    if "Approved plan:" in system or any("Approved plan" in m["content"] for m in msgs if m["role"] == "system"):
        done = {m.get("tool_name") for m in msgs if m["role"] == "tool"}
        for line in "\n".join(m["content"] for m in msgs if m["role"] == "system").splitlines():
            m = re.match(r"\d+\. (\w+) (\{.*?\}) -", line)
            if m and m.group(1) not in done and m.group(1) in tools:
                return "", [{"function": {"name": m.group(1), "arguments": json.loads(m.group(2))}}]
        return "Plan finished.", []
    if last["role"] == "tool":
        try:
            res = json.loads(last["content"])
        except ValueError:
            res = {"ok": False, "message": last["content"]}
        if res.get("ok"):
            return f"Done - {res.get('message')}", []
        return f"That didn't work: {res.get('message')}", []
    t = last_user.lower()
    if "system_info" in tools and re.search(r"system|ram|cpu|memory", t):
        return "Let me check.", [{"function": {"name": "system_info", "arguments": {}}}]
    if "create_text_file" in tools and re.search(r"\bnote\b|\bfile\b", t):
        return "", [{"function": {"name": "create_text_file", "arguments": {"path": "fristy-note.txt", "content": "Hello from FRISTY"}}}]
    if re.search(r"[֐-׿]", last_user):
        return "שלום! אני FRISTY. זו תשובת בדיקה משרת המודל המדומה.", []
    return ("Hello! I'm **FRISTY** running on a *mock* model for testing.\n\n"
            "- Ask about your **system** to see a tool call\n- Ask me to create a **note**\n\n```python\nprint('hi')\n```"), []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            return self._json({"models": [{"name": m, "size": 1_000_000_000} for m in INSTALLED]})
        if self.path == "/api/version":
            return self._json({"version": "0.9.0-mock"})
        self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        self.do_POST()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/show":
            vision = "gemma3" in body.get("model", "") or "vl" in body.get("model", "")
            return self._json({"capabilities": ["completion", "vision"] if vision else ["completion", "tools"]})
        if self.path == "/api/pull":
            # Simulated download: ~8 s, 2 GB "layer", like a real Ollama pull stream.
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            total = 2_000_000_000
            self.wfile.write(b'{"status":"pulling manifest"}\n')
            for i in range(41):
                ev = {"status": "pulling 6a0746a1ec1a", "digest": "sha256:6a07", "total": total, "completed": total * i // 40}
                self.wfile.write((json.dumps(ev) + "\n").encode())
                self.wfile.flush()
                time.sleep(0.2)
            for st in ("verifying sha256 digest", "writing manifest", "success"):
                self.wfile.write((json.dumps({"status": st}) + "\n").encode())
            if body.get("model") not in INSTALLED:
                INSTALLED.append(body.get("model"))
            return
        if self.path == "/api/delete":
            if body.get("model") in INSTALLED:
                INSTALLED.remove(body.get("model"))
            return self._json({})
        if self.path != "/api/chat":
            return self._json({"error": "not found"}, 404)
        text, calls = respond(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for word in re.findall(r"\S+\s*|\n", text):
            self.wfile.write((json.dumps({"message": {"role": "assistant", "content": word}, "done": False}) + "\n").encode())
            self.wfile.flush()
            time.sleep(0.02)
        if calls:
            self.wfile.write((json.dumps({"message": {"role": "assistant", "content": "", "tool_calls": calls}, "done": False}) + "\n").encode())
        self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop",
                                      "prompt_eval_count": 42, "eval_count": len(text.split())}) + "\n").encode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11434)
    ap.add_argument("--empty", action="store_true", help="start with no installed models")
    a = ap.parse_args()
    if a.empty:
        INSTALLED.clear()
    print(f"mock ollama on 127.0.0.1:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
