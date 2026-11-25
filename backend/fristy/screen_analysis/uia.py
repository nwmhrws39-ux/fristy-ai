"""Windows UI Automation access on a dedicated COM thread.

UI Automation is the preferred, reliable way to find buttons/fields: it gives
names, control types and exact bounding boxes without guessing from pixels.
Password fields are never returned and never typed into.
"""
from __future__ import annotations

import concurrent.futures
import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

from ..computer_control.base import ActionError

MAX_ELEMENTS = 250
INTERESTING = {
    "ButtonControl", "EditControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl",
    "ListItemControl", "MenuItemControl", "TabItemControl", "HyperlinkControl", "TreeItemControl",
    "TextControl", "DocumentControl", "SplitButtonControl", "SliderControl", "DataItemControl",
}


@dataclass
class UIElement:
    id: str
    name: str
    control_type: str
    automation_id: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom (screen pixels)
    enabled: bool
    depth: int

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["center"] = self.center
        return d


class UIAWorker:
    def __init__(self) -> None:
        self.available = sys.platform == "win32"
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._controls: dict[str, Any] = {}
        self._elements: dict[str, UIElement] = {}
        self._snapshot_at = 0.0
        self._lock = threading.Lock()

    def _init_thread(self) -> None:
        import comtypes  # type: ignore

        comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)

    def _run(self, fn, *args, timeout: float = 15.0):
        if not self.available:
            raise ActionError("UI Automation is only available on Windows.", "unsupported_platform")
        with self._lock:
            if self._executor is None:
                self._executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="uia", initializer=self._init_thread)
        return self._executor.submit(fn, *args).result(timeout=timeout)

    # ------------------------------------------------------------------ api
    def snapshot(self, max_depth: int = 14) -> list[UIElement]:
        return self._run(self._snapshot, max_depth)

    def _snapshot(self, max_depth: int) -> list[UIElement]:
        import uiautomation as auto  # type: ignore

        root = auto.GetForegroundControl()
        if root is None:
            return []
        try:
            root = root.GetTopLevelControl() or root
        except Exception:
            pass
        elements: list[UIElement] = []
        controls: dict[str, Any] = {}
        for control, depth in auto.WalkControl(root, includeTop=True, maxDepth=max_depth):
            if len(elements) >= MAX_ELEMENTS:
                break
            try:
                ctype = control.ControlTypeName
                if ctype not in INTERESTING:
                    continue
                if ctype == "EditControl" and self._is_password(control):
                    continue  # never expose password fields
                rect = control.BoundingRectangle
                if rect.width() <= 0 or rect.height() <= 0:
                    continue
                name = (control.Name or "").strip()
                if ctype == "TextControl" and not name:
                    continue
                eid = f"e{len(elements) + 1}"
                elements.append(UIElement(
                    id=eid, name=name[:120], control_type=ctype.replace("Control", ""),
                    automation_id=(control.AutomationId or "")[:80],
                    rect=(rect.left, rect.top, rect.right, rect.bottom),
                    enabled=bool(control.IsEnabled), depth=depth,
                ))
                controls[eid] = control
            except Exception:
                continue
        self._controls = controls
        self._elements = {e.id: e for e in elements}
        self._snapshot_at = time.time()
        return elements

    @staticmethod
    def _is_password(control) -> bool:
        try:
            import uiautomation as auto  # type: ignore

            return bool(control.GetPropertyValue(auto.PropertyId.IsPasswordProperty))
        except Exception:
            return True  # unknown -> treat as sensitive

    def focused_is_password(self) -> bool:
        if not self.available:
            return False
        return self._run(self._focused_is_password, timeout=5)

    def _focused_is_password(self) -> bool:
        import uiautomation as auto  # type: ignore

        c = auto.GetFocusedControl()
        return bool(c and c.ControlTypeName == "EditControl" and self._is_password(c))

    def element(self, eid: str) -> UIElement:
        e = self._elements.get(eid)
        if not e:
            raise ActionError(f"Element {eid} not found. Call list_ui_elements first to refresh element ids.",
                              "element_not_found")
        if time.time() - self._snapshot_at > 120:
            raise ActionError("Element list is stale (older than 2 minutes); list the UI elements again.",
                              "stale_elements")
        return e

    def find(self, query: str) -> list[UIElement]:
        q = query.lower().strip()
        els = self.snapshot()
        exact = [e for e in els if e.name.lower() == q]
        return exact or [e for e in els if q and q in e.name.lower()]

    def invoke(self, eid: str) -> bool:
        """Use the element's InvokePattern / TogglePattern / SelectionItem (no mouse needed)."""
        self.element(eid)
        return self._run(self._invoke, eid)

    def _invoke(self, eid: str) -> bool:
        c = self._controls.get(eid)
        if c is None:
            return False
        for getter, method in (("GetInvokePattern", "Invoke"), ("GetTogglePattern", "Toggle"),
                               ("GetSelectionItemPattern", "Select"), ("GetExpandCollapsePattern", "Expand")):
            try:
                pattern = getattr(c, getter)()
                if pattern:
                    getattr(pattern, method)()
                    return True
            except Exception:
                continue
        return False

    def set_text(self, eid: str, text: str) -> bool:
        self.element(eid)
        return self._run(self._set_text, eid, text)

    def _set_text(self, eid: str, text: str) -> bool:
        c = self._controls.get(eid)
        if c is None:
            return False
        if c.ControlTypeName == "EditControl" and self._is_password(c):
            raise ActionError("Refusing to type into a password field.", "sensitive_field")
        try:
            vp = c.GetValuePattern()
            if vp and not vp.IsReadOnly:
                vp.SetValue(text)
                return True
        except Exception:
            pass
        return False
