"""B32: win_event_hook 完整单测（不触发真实 Win32 消息循环）。"""
import time

import win_event_hook as wh


class FakeUser32:
    def __init__(self, handle=123, peek_results=None, raise_set=False, raise_unhook=False):
        self.handle = handle
        self.peek_results = list(peek_results or [])
        self.raise_set = raise_set
        self.raise_unhook = raise_unhook
        self.unhook_calls = []

    def SetWinEventHook(self, *args):
        if self.raise_set:
            raise OSError("set hook failed")
        return self.handle

    def UnhookWinEvent(self, handle):
        self.unhook_calls.append(handle)
        if self.raise_unhook:
            raise OSError("unhook failed")
        return 1

    def PeekMessageW(self, msg_ref, hwnd, min_msg, max_msg, remove):
        if self.peek_results:
            return self.peek_results.pop(0)
        return 0


def test_event_callback_throttles_and_calls(monkeypatch):
    calls = []
    hook = wh.WinEventHook(lambda: calls.append(1))
    hook._last_trigger_ts = 0
    monkeypatch.setattr(wh.time, "time", lambda: 100.0)
    hook._event_callback(None, 0, 0, 0, 0, 0, 0)
    assert calls == [1]
    # 同一时间窗口内第二次被节流
    hook._event_callback(None, 0, 0, 0, 0, 0, 0)
    assert calls == [1]
    # 超过窗口后再次触发
    monkeypatch.setattr(wh.time, "time", lambda: 106.0)
    hook._event_callback(None, 0, 0, 0, 0, 0, 0)
    assert calls == [1, 1]


def test_event_callback_swallows_user_exception():
    def boom():
        raise RuntimeError("user callback failed")

    hook = wh.WinEventHook(boom)
    hook._last_trigger_ts = 0
    hook._event_callback(None, 0, 0, 0, 0, 0, 0)  # 不应抛出


def test_start_existing_and_null_handle(monkeypatch):
    monkeypatch.setattr(wh, "user32", FakeUser32())
    hook = wh.WinEventHook(lambda: None)
    hook._hook_handle = 9
    assert hook.start() is True
    hook._hook_handle = None
    monkeypatch.setattr(wh, "user32", FakeUser32(handle=0))
    assert hook.start() is False


def test_start_exception_clears_proc(monkeypatch):
    monkeypatch.setattr(wh, "user32", FakeUser32(raise_set=True))
    hook = wh.WinEventHook(lambda: None)
    assert hook.start() is False
    assert hook._proc_ref is None


def test_stop_no_handle_and_unhook(monkeypatch):
    fake = FakeUser32()
    monkeypatch.setattr(wh, "user32", fake)
    hook = wh.WinEventHook(lambda: None)
    hook.stop()
    assert hook._hook_handle is None

    hook._hook_handle = 77
    hook.stop()
    assert fake.unhook_calls == [77]
    assert hook._hook_handle is None


def test_stop_unhook_exception_still_clears(monkeypatch):
    monkeypatch.setattr(wh, "user32", FakeUser32(raise_unhook=True))
    hook = wh.WinEventHook(lambda: None)
    hook._hook_handle = 88
    hook.stop()
    assert hook._hook_handle is None
    assert hook._proc_ref is None


def test_pump_messages_no_hook_and_messages(monkeypatch):
    fake = FakeUser32(peek_results=[1, 1, 0])
    monkeypatch.setattr(wh, "user32", fake)
    hook = wh.WinEventHook(lambda: None)
    hook.pump_messages()  # 无 handle 直接返回
    hook._hook_handle = 1
    hook.pump_messages(max_iterations=5)
    # PeekMessageW 返回 1,1,0 → 处理两条后 break


def test_install_uninstall_and_pump(monkeypatch):
    fake = FakeUser32(peek_results=[0])
    monkeypatch.setattr(wh, "user32", fake)
    monkeypatch.setattr(wh, "_global_hook", None)
    hook = wh.install(lambda: None)
    assert hook is not None
    assert wh.install(lambda: None) is hook  # 已存在直接返回
    wh.pump()
    wh.uninstall()
    assert wh._global_hook is None
    # 再卸载一次不报错
    wh.uninstall()


def test_install_failure_returns_none(monkeypatch):
    monkeypatch.setattr(wh, "user32", FakeUser32(handle=0))
    monkeypatch.setattr(wh, "_global_hook", None)
    assert wh.install(lambda: None) is None
