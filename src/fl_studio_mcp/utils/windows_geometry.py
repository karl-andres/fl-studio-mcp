"""Inspect and reposition supported FL Studio windows on Windows."""

from __future__ import annotations

import ctypes as ct
import sys
import threading
import time
from contextlib import contextmanager
from ctypes import wintypes as w

_MOVE_LOCK = threading.Lock()

_FORMS = {
    "TFruityLoopsMainForm": "main",
    "TEventEditForm": "playlist",
    "TFXForm": "mixer",
    "TStepSeqForm": "channel_rack",
    "TPianoRollForm": "piano_roll",
    "TSampleListForm": "browser",
    "TPluginForm": "plugin_editor",
    "TSynthEditorForm": "plugin_editor",
}


def _user32():
    if sys.platform != "win32":
        raise RuntimeError("Window geometry tools require Windows")
    return ct.windll.user32


def _api(library, name, result, *args):
    function = getattr(library, name)
    function.argtypes = args
    function.restype = result
    return function


@contextmanager
def _physical_pixels(user):
    set_context = _api(user, "SetThreadDpiAwarenessContext", w.HANDLE, w.HANDLE)
    previous = set_context(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    if not previous:
        raise RuntimeError("Could not select physical screen coordinates")
    try:
        yield
    finally:
        set_context(previous)


def _handles(user, parent=None):
    callback_type = ct.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    found = []

    @callback_type
    def collect(hwnd, _):
        found.append(hwnd)
        return True

    if parent is None:
        _api(user, "EnumWindows", w.BOOL, callback_type, w.LPARAM)(collect, 0)
    else:
        _api(user, "EnumChildWindows", w.BOOL, w.HWND, callback_type, w.LPARAM)(parent, collect, 0)
    return found


def _window_string(user, hwnd, name):
    buffer = ct.create_unicode_buffer(1024)
    length = _api(user, name, ct.c_int, w.HWND, w.LPWSTR, ct.c_int)(hwnd, buffer, len(buffer))
    if length >= len(buffer) - 1:
        raise ValueError("Window title or class exceeds the supported length")
    return buffer.value


def _class(user, hwnd):
    return _window_string(user, hwnd, "GetClassNameW")


def _pid(user, hwnd):
    pid = w.DWORD()
    _api(user, "GetWindowThreadProcessId", w.DWORD, w.HWND, ct.POINTER(w.DWORD))(
        hwnd, ct.byref(pid)
    )
    return pid.value


def _root(user, hwnd):
    return _api(user, "GetAncestor", w.HWND, w.HWND, w.UINT)(hwnd, 2)  # GA_ROOT


def _visible(user, hwnd):
    visible = _api(user, "IsWindowVisible", w.BOOL, w.HWND)
    iconic = _api(user, "IsIconic", w.BOOL, w.HWND)
    return visible(hwnd) and not iconic(_root(user, hwnd))


def _bounds(user, hwnd):
    rect = w.RECT()
    if not _api(user, "GetWindowRect", w.BOOL, w.HWND, ct.POINTER(w.RECT))(hwnd, ct.byref(rect)):
        raise RuntimeError("Windows did not return the window bounds")
    return rect.left, rect.top, rect.right, rect.bottom


def _fl_pids(user, top):
    return {_pid(user, hwnd) for hwnd in top if _class(user, hwnd) == "TFruityLoopsMainForm"} - {0}


def _fl_handles(user):
    top = _handles(user)
    fl_pids = _fl_pids(user, top)
    candidates = [hwnd for hwnd in top if _pid(user, hwnd) in fl_pids]
    return fl_pids, dict.fromkeys(
        hwnd for parent in candidates for hwnd in (parent, *_handles(user, parent))
    )


def _describe(user, hwnd, fl_pids):
    pid = _pid(user, hwnd)
    kind = _class(user, hwnd)
    if pid not in fl_pids or kind not in _FORMS or not _visible(user, hwnd):
        raise ValueError("Expected a visible FL Studio form; refresh the window list")
    return {
        "hwnd": hwnd,
        "pid": pid,
        "class_name": kind,
        "kind": _FORMS[kind],
        "title": _window_string(user, hwnd, "GetWindowTextW"),
        "bounds": _bounds(user, hwnd),
    }


def list_windows() -> list[dict]:
    """Discover visible supported forms and their physical screen rectangles."""
    user = _user32()
    with _physical_pixels(user):
        fl_pids, handles = _fl_handles(user)
        result = []
        for hwnd in handles:
            try:
                result.append(_describe(user, hwnd, fl_pids))
            except ValueError:
                continue
        return result


def _request_position(user, hwnd, x, y, width, height, resize):
    get_style = _api(user, "GetWindowLongW", w.LONG, w.HWND, ct.c_int)
    if get_style(hwnd, -16) & 0x40000000:  # WS_CHILD coordinates are parent-relative.
        parent = _api(user, "GetParent", w.HWND, w.HWND)(hwnd)
        point = w.POINT(x, y)
        to_client = _api(user, "ScreenToClient", w.BOOL, w.HWND, ct.POINTER(w.POINT))
        if not parent or not to_client(parent, ct.byref(point)):
            raise RuntimeError("Could not convert the requested position into parent coordinates")
        x, y = point.x, point.y
    # Queue the request to FL's UI thread without activating the window or changing its Z order.
    flags = 0x4000 | 0x0010 | 0x0004  # ASYNCWINDOWPOS | NOACTIVATE | NOZORDER
    if not resize:
        flags |= 0x0001  # NOSIZE
    set_position = _api(
        user, "SetWindowPos", w.BOOL, w.HWND, w.HWND, *([ct.c_int] * 4), w.UINT
    )
    if not set_position(hwnd, None, x, y, width, height, flags):
        raise RuntimeError("Windows did not accept the window move")


def move_window(
    hwnd: int,
    expected_pid: int,
    expected_title: str,
    expected_bounds: tuple[int, int, int, int],
    x: int,
    y: int,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    """Request a move and return actual bounds after a short, bounded readback."""
    if type(hwnd) is not int or not 0 < hwnd < 1 << (ct.sizeof(w.HWND) * 8):
        raise ValueError("Expected a valid window handle")
    if any(type(pos) is not int or not -32768 <= pos <= 32767 for pos in (x, y)):
        raise ValueError("Coordinates must be physical screen pixels in -32768..32767")
    resize = width is not None or height is not None
    if resize and (
        type(width) is not int
        or type(height) is not int
        or not 80 <= width <= 16384
        or not 40 <= height <= 16384
    ):
        raise ValueError("Supply both width and height (80..16384 by 40..16384) to resize")

    user = _user32()
    with _MOVE_LOCK, _physical_pixels(user):
        fl_pids = _fl_pids(user, _handles(user))
        if expected_pid not in fl_pids:
            raise ValueError("FL Studio instance is no longer available; refresh the window list")
        before = _describe(user, hwnd, {expected_pid})
        if before["title"] != expected_title or before["bounds"] != expected_bounds:
            raise ValueError("Window title or bounds changed; refresh the window list")
        maximized = _api(user, "IsZoomed", w.BOOL, w.HWND)
        if maximized(hwnd) or maximized(_root(user, hwnd)) and before["kind"] == "main":
            raise ValueError("Restore the maximized form before moving it")
        left, top, right, bottom = before["bounds"]
        requested_width = width if resize else right - left
        requested_height = height if resize else bottom - top
        requested = (x, y, x + requested_width, y + requested_height)
        _request_position(user, hwnd, x, y, requested_width, requested_height, resize)

        deadline = time.monotonic() + 0.6
        observed = None
        while True:
            try:
                current = _describe(user, hwnd, {expected_pid})
            except (ValueError, RuntimeError):
                break
            if (current["title"], current["class_name"]) != (expected_title, before["class_name"]):
                break
            observed = current["bounds"]
            if observed == requested or time.monotonic() >= deadline:
                break
            time.sleep(0.03)
        return {
            "submitted": True,
            "verified_geometry": observed == requested,
            "before": before["bounds"],
            "requested": requested,
            "observed": observed,
        }
