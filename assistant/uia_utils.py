"""
UIA (UI Automation) helpers for Windows accessibility tree.
Provides element inspection, find-by-name/role, click, and focused-element queries.
"""

import logging
from typing import Optional

logger = logging.getLogger("buddy.uia_utils")

_UIA_AVAILABLE = False
try:
    import uiautomation as auto
    _UIA_AVAILABLE = True
except ImportError:
    pass

CONTROL_TYPE_NAMES = {
    50020: "Window", 50000: "Button", 50002: "Edit", 50030: "ListItem",
    50033: "MenuItem", 50034: "Menu", 50004: "ComboBox", 50012: "Hyperlink",
    50022: "Tab", 50008: "CheckBox", 50010: "RadioButton", 50032: "List",
    50036: "ProgressBar", 50037: "ScrollBar", 50038: "Slider", 50001: "Calendar",
    50003: "Custom", 50005: "DataGrid", 50006: "DataItem", 50007: "Document",
    50009: "Group", 50011: "Header", 50013: "Image", 50015: "Pane",
    50016: "Image", 50017: "Separator", 50018: "SemanticZoom", 50019: "Thumb",
    50021: "TitleBar", 50023: "ToolBar", 50024: "ToolTip", 50025: "Tree",
    50026: "TreeItem", 50027: "Custom", 50028: "Spinner", 50029: "SplitButton",
    50031: "AppBar", 50035: "Navigation",
}

_CONTROL_TYPE_NAMES_REVERSE = {v: k for k, v in CONTROL_TYPE_NAMES.items()}


def _control_to_dict(control, depth=0, max_depth=3):
    if control is None or depth > max_depth:
        return None
    try:
        rect = control.BoundingRectangle
        rect_str = str(rect) if rect else ""
        result = {
            "name": control.Name or "",
            "role": CONTROL_TYPE_NAMES.get(control.ControlType, f"Type_{control.ControlType}"),
            "rect": rect_str,
            "enabled": control.IsEnabled,
        }
        if depth < max_depth:
            children = []
            child = control.GetFirstChildControl()
            while child:
                child_dict = _control_to_dict(child, depth + 1, max_depth)
                if child_dict:
                    children.append(child_dict)
                child = child.GetNextSiblingControl()
            result["children"] = children
        return result
    except Exception as e:
        logger.debug(f"Error converting control: {e}")
        return None


def get_focused() -> Optional[dict]:
    """Return info about the currently focused UI element."""
    if not _UIA_AVAILABLE:
        return None
    try:
        control = auto.GetFocusedControl()
        return _control_to_dict(control, max_depth=1) if control else None
    except Exception as e:
        logger.warning(f"Failed to get focused element: {e}")
        return None


def get_active_window() -> Optional[dict]:
    """Return info about the currently active window (top-level)."""
    if not _UIA_AVAILABLE:
        return None
    try:
        focused = auto.GetFocusedControl()
        if focused:
            top = focused.GetTopWindow()
            return _control_to_dict(top, max_depth=1) if top else None
    except Exception as e:
        logger.warning(f"Failed to get active window: {e}")
    return None


def find_elements(name: str = "", role: str = "", max_results: int = 10) -> list[dict]:
    """Find UI elements by name and/or role. Returns up to max_results."""
    if not _UIA_AVAILABLE:
        return []
    try:
        root = auto.GetRootControl()
        conditions = []

        if name:
            conditions.append(
                auto.PropertyCondition(auto.Control.NameProperty, name)
            )
        if role:
            ctrl_id = _CONTROL_TYPE_NAMES_REVERSE.get(role.capitalize())
            if ctrl_id:
                conditions.append(
                    auto.PropertyCondition(auto.Control.ControlTypeProperty, ctrl_id)
                )

        if not conditions:
            return []

        condition = conditions[0] if len(conditions) == 1 else auto.AndCondition(*conditions)
        elements = root.FindAll(auto.TreeScope.Descendants, condition)

        results = []
        for el in elements[:max_results]:
            d = _control_to_dict(el, max_depth=1)
            if d:
                results.append(d)
        return results
    except Exception as e:
        logger.warning(f"Failed to find elements: {e}")
        return []


def list_visible(depth: int = 3) -> list[dict]:
    """List visible UI tree under the active (focused) window."""
    if not _UIA_AVAILABLE:
        return []
    try:
        focused = auto.GetFocusedControl()
        if focused:
            top = focused.GetTopWindow()
            if top:
                return [_control_to_dict(top, max_depth=depth)]
    except Exception as e:
        logger.warning(f"Failed to list visible elements: {e}")
    return []


def click_element(name: str) -> bool:
    """Find a UI element by exact name and click it."""
    if not _UIA_AVAILABLE:
        return False
    try:
        element = auto.FindControl(auto.GetRootControl(), lambda c, d: c.Name == name)
        if element:
            element.Click()
            return True
        logger.info(f"Element '{name}' not found")
        return False
    except Exception as e:
        logger.warning(f"Failed to click element '{name}': {e}")
        return False


def get_element_info(name: str) -> Optional[dict]:
    """Get details about a UI element by name."""
    if not _UIA_AVAILABLE:
        return None
    try:
        element = auto.FindControl(auto.GetRootControl(), lambda c, d: c.Name == name)
        if element:
            return _control_to_dict(element, max_depth=2)
    except Exception as e:
        logger.warning(f"Failed to get element '{name}': {e}")
    return None


def wait_for_element(name: str, timeout: float = 5.0) -> Optional[dict]:
    """Wait for a UI element to appear (polling). Returns element info or None."""
    if not _UIA_AVAILABLE:
        return None
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            element = auto.FindControl(auto.GetRootControl(), lambda c, d: name.lower() in (c.Name or "").lower())
            if element:
                return _control_to_dict(element, max_depth=1)
        except Exception:
            pass
        time.sleep(0.3)
    return None
