from datetime import datetime

import pytest

from fristy.computer_control.base import ActionError

GAMING = {"name": "Gaming Mode", "trigger": {"type": "phrase", "phrases": ["gaming mode", "מצב גיימינג"]},
          "confirmation": "once",
          "steps": [{"action": "launch_app", "args": {"name": "Discord"}},
                    {"action": "launch_game", "args": {"name": "GTA V"}},
                    {"action": "set_volume", "args": {"level": 50}}]}


def test_validation(svc):
    with pytest.raises(ActionError):
        svc.automations.save({**GAMING, "steps": [{"action": "rm_rf", "args": {}}]})
    with pytest.raises(ActionError):
        svc.automations.save({**GAMING, "steps": [{"action": "set_volume", "args": {"level": 900}}]})
    with pytest.raises(ActionError):
        svc.automations.save({**GAMING, "steps": [{"action": "run_custom_command", "args": {"name": "x"}}]})
    with pytest.raises(Exception):
        svc.automations.save({**GAMING, "trigger": {"type": "schedule", "time": "25:99"}})


def test_phrase_matching(svc):
    a = svc.automations.save(GAMING)
    assert svc.automations.match_phrase("Gaming mode!")["id"] == a["id"]
    assert svc.automations.match_phrase("run gaming mode")["id"] == a["id"]
    assert svc.automations.match_phrase("מצב גיימינג")["id"] == a["id"]
    assert svc.automations.match_phrase("what is gaming") is None
    svc.automations.set_enabled(a["id"], False)
    assert svc.automations.match_phrase("gaming mode") is None


async def test_run_with_confirmation_once(svc, approve_all):
    a = svc.automations.save(GAMING)
    res = await svc.automations.run(a["id"])
    assert res.ok, res.message
    assert len(approve_all.asked) == 1 and approve_all.asked[0]["action"] == "automation"
    assert [c[1] for c in svc.platform.calls if c[0] == "launch"] == ["Discord", "Grand Theft Auto V"]
    assert svc.platform.volume == 50
    assert svc.automations.get(a["id"])["last_run_at"]


async def test_run_denied(svc, approve_all):
    approve_all.decision["value"] = False
    a = svc.automations.save(GAMING)
    res = await svc.automations.run(a["id"])
    assert res.code == "not_approved" and svc.platform.calls == []


async def test_stop_on_error_and_continue(svc, approve_all):
    data = {**GAMING, "steps": [{"action": "launch_app", "args": {"name": "Nope Nope App"}},
                                {"action": "set_volume", "args": {"level": 10}}]}
    a = svc.automations.save(data)
    res = await svc.automations.run(a["id"])
    assert not res.ok and svc.platform.volume == 50 and "skipped" in res.message
    data["steps"][0]["continue_on_error"] = True
    svc.automations.save(data, a["id"])
    res = await svc.automations.run(a["id"])
    assert not res.ok and svc.platform.volume == 10 and res.code == "partial_failure"


async def test_high_risk_steps_still_confirmed(svc, approve_all):
    from conftest import enable
    enable(svc, "power_management")
    a = svc.automations.save({"name": "Good Night", "trigger": {"type": "phrase", "phrases": ["good night"]},
                              "steps": [{"action": "shutdown_computer", "args": {"delay_seconds": 600}}]})
    res = await svc.automations.run(a["id"])
    assert res.ok
    assert [x["action"] for x in approve_all.asked] == ["automation", "shutdown_computer"]


def test_conditions(svc):
    eng = svc.automations
    assert eng.check_conditions([{"type": "time_between", "start": "22:00", "end": "02:00"}],
                                datetime(2026, 1, 1, 23, 30)) is None
    assert eng.check_conditions([{"type": "time_between", "start": "22:00", "end": "02:00"}],
                                datetime(2026, 1, 1, 12, 0))
    assert eng.check_conditions([{"type": "process_running", "process": "notepad"}]) is None
    assert eng.check_conditions([{"type": "process_not_running", "process": "notepad"}])
    assert eng.check_conditions([{"type": "weekday", "days": [5, 6]}], datetime(2026, 11, 25))  # Wednesday


def test_schedule_due(svc):
    a = svc.automations.save({"name": "Evening", "trigger": {"type": "schedule", "time": "21:15", "days": [2]},
                              "steps": [{"action": "set_volume", "args": {"level": 20}}]})
    assert [x["id"] for x in svc.automations.due(datetime(2026, 11, 25, 21, 15))] == [a["id"]]
    assert svc.automations.due(datetime(2026, 11, 25, 21, 16)) == []
    assert svc.automations.due(datetime(2026, 11, 26, 21, 15)) == []


async def test_chat_triggers_custom_command(svc, approve_all):
    import asyncio
    svc.automations.save(GAMING)
    q = svc.bus.subscribe()
    svc.orchestrator.start("gaming mode")
    while True:
        ev = await asyncio.wait_for(q.get(), 5)
        if ev["type"] == "chat.done":
            break
    assert "3/3 steps succeeded" in ev["text"]


def test_templates_are_valid_shape(svc):
    from fristy.automations.models import TEMPLATES, Automation
    for t in TEMPLATES:
        Automation.model_validate(t)
