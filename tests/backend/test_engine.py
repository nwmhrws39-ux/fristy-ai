import asyncio

import pytest
from pydantic import BaseModel

from fristy.computer_control.base import ActionError, ActionResult, ActionSpec, ExecutionContext, Risk
from conftest import enable


class P(BaseModel):
    n: int = 1


def _spec(name, risk=Risk.LOW, perm=None, handler=None, **kw):
    async def ok(ctx, a):
        return ActionResult(True, f"did {a.n}")
    return ActionSpec(name=name, description="t", params=P, permission=perm, risk=risk, handler=handler or ok, **kw)


async def test_unknown_action_rejected_and_audited(svc):
    res = await svc.engine.execute("format_c_drive", {})
    assert not res.ok and res.code == "unknown_action"
    assert svc.audit.recent(1)[0]["event"] == "action.rejected"


async def test_invalid_arguments(svc):
    res = await svc.engine.execute("set_volume", {"level": 400})
    assert not res.ok and res.code == "invalid_arguments"


async def test_permission_denied_by_default(svc):
    assert svc.settings.current.permissions["power_management"] is False
    res = await svc.engine.execute("lock_computer", {})
    assert res.code == "permission_denied"
    assert ("lock",) not in svc.platform.calls


async def test_high_risk_requires_confirmation_and_denial_blocks(svc, approve_all):
    enable(svc, "power_management")
    approve_all.decision["value"] = False
    res = await svc.engine.execute("shutdown_computer", {"delay_seconds": 30}, ExecutionContext(source="ui"))
    assert not res.ok and res.code == "not_approved"
    assert not any(c[0] == "shutdown" for c in svc.platform.calls)
    assert approve_all.asked[0]["risk"] == "high"


async def test_high_risk_approved_executes(svc, approve_all):
    enable(svc, "power_management")
    res = await svc.engine.execute("shutdown_computer", {"delay_seconds": 30})
    assert res.ok
    assert ("shutdown", 30, False) in svc.platform.calls


async def test_no_ui_connected_fails_closed(svc):
    enable(svc, "power_management")
    svc.confirmations.ui_connected = lambda: False
    res = await svc.engine.execute("restart_computer", {"delay_seconds": 5})
    assert res.code == "not_approved"


async def test_confirmation_timeout_denies(svc):
    enable(svc, "power_management")
    svc.confirmations.timeout = 0.05
    res = await svc.engine.execute("restart_computer", {"delay_seconds": 5})
    assert res.code == "not_approved"
    assert svc.confirmations.pending() == []


async def test_broker_resolve_roundtrip(svc):
    enable(svc, "power_management")
    q = svc.bus.subscribe()
    task = asyncio.create_task(svc.engine.execute("restart_computer", {"delay_seconds": 5}))
    while True:
        ev = await asyncio.wait_for(q.get(), 2)
        if ev["type"] == "confirmation.request":
            break
    assert svc.confirmations.resolve(ev["id"], True)
    res = await task
    assert res.ok and ("shutdown", 5, True) in svc.platform.calls


async def test_medium_risk_confirmation_depends_on_source(svc, approve_all):
    svc.registry.register(_spec("t_medium", Risk.MEDIUM))
    assert (await svc.engine.execute("t_medium", {}, ExecutionContext(source="ui"))).ok
    assert approve_all.asked == []
    await svc.engine.execute("t_medium", {}, ExecutionContext(source="agent"))
    assert len(approve_all.asked) == 1
    await svc.engine.execute("t_medium", {}, ExecutionContext(source="agent", preapproved={"t_medium"}))
    assert len(approve_all.asked) == 1
    await svc.engine.execute("t_medium", {}, ExecutionContext(source="chat", untrusted_seen=True,
                                                               preapproved={"t_medium"}))
    assert len(approve_all.asked) == 2  # untrusted content escalates even pre-approved actions


async def test_handler_exception_is_failure_not_success(svc):
    async def boom(ctx, a):
        raise OSError("disk on fire")
    svc.registry.register(_spec("t_boom", handler=boom))
    res = await svc.engine.execute("t_boom", {})
    assert not res.ok and "disk on fire" in res.message and res.code == "exception"
    assert svc.audit.recent(1)[0]["status"] == "exception"


async def test_handler_action_error(svc):
    async def err(ctx, a):
        raise ActionError("nope", "custom")
    svc.registry.register(_spec("t_err", handler=err))
    res = await svc.engine.execute("t_err", {})
    assert (res.ok, res.code) == (False, "custom")


async def test_timeout(svc):
    async def slow(ctx, a):
        await asyncio.sleep(5)
        return ActionResult(True, "late")
    svc.registry.register(_spec("t_slow", handler=slow))
    res = await svc.engine.execute("t_slow", {}, timeout=0.05)
    assert res.code == "timeout" and not res.ok


async def test_windows_only_on_other_platform(svc):
    svc.engine.is_windows = False
    res = await svc.engine.execute("set_volume", {"level": 10})
    assert res.code == "unsupported_platform"


async def test_dry_run_does_not_execute(svc):
    res = await svc.engine.execute("set_volume", {"level": 10}, ExecutionContext(dry_run=True))
    assert res.code == "dry_run" and ("set_volume", 10) not in svc.platform.calls


async def test_emergency_stop_cancels_task(svc):
    async def forever():
        await asyncio.sleep(100)
    t = asyncio.create_task(forever())
    svc.stop.register("r1", t)
    assert svc.stop.emergency_stop() == 1
    with pytest.raises(asyncio.CancelledError):
        await t


def test_catalog_lists_every_action(svc):
    cat = svc.engine.catalog()
    names = {c["name"] for c in cat}
    for required in ("launch_app", "open_website", "switch_window", "minimize_window", "maximize_window",
                     "close_app", "set_volume", "media_control", "take_screenshot", "lock_computer",
                     "restart_computer", "shutdown_computer", "find_files", "open_folder", "system_info",
                     "analyze_screen", "click_element", "scroll", "type_text", "run_terminal_command",
                     "write_code_file", "remember", "pc_performance", "fristy_launcher_launch"):
        assert required in names, required
    for c in cat:
        assert c["schema"]["type"] == "object"
