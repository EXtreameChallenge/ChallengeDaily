"""B32: screenshot 模块单测（不依赖真实屏幕）。"""
from pathlib import Path
import time

from PIL import Image

import screenshot as ss
import screenshot_crypto as sc


class FakeShot:
    def __init__(self, size=(2, 2), bgra=None):
        self.size = size
        self.bgra = bgra or bytes([0, 0, 255, 255] * (size[0] * size[1]))


class FakeSct:
    def __init__(self, shot=None):
        self.shot = shot or FakeShot()
        self.grabbed = []

    def grab(self, monitor):
        self.grabbed.append(monitor)
        return self.shot


def _reset_globals(monkeypatch):
    monkeypatch.setattr(ss, "_last_phash", None)
    monkeypatch.setattr(ss, "_consecutive_duplicates", 0)
    monkeypatch.setattr(ss, "_last_saved_filepath", "")
    monkeypatch.setattr(ss, "_last_saved_filename", "")


def test_phash_and_distance():
    img = Image.new("RGB", (16, 16))
    for x in range(16):
        for y in range(16):
            img.putpixel((x, y), (x * 8, y * 8, 0))
    h1 = ss._compute_phash(img)
    h2 = ss._compute_phash(img)
    assert h1 == h2
    assert ss._phash_distance(h1, h2) == 0
    assert ss._phash_distance(0, 1) == 1
    img.close()


def test_is_screen_duplicate_first_and_repeat(monkeypatch):
    _reset_globals(monkeypatch)
    img1 = Image.new("RGB", (8, 8), (0, 0, 0))
    img2 = Image.new("RGB", (8, 8), (0, 0, 0))
    assert ss.is_screen_duplicate(img1) is False
    assert ss.is_screen_duplicate(img2) is True
    img3 = Image.new("RGB", (8, 8))
    for x in range(8):
        for y in range(8):
            img3.putpixel((x, y), (255 if (x + y) % 2 else 0, 0, 0))
    assert ss.is_screen_duplicate(img3) is False
    img1.close(); img2.close(); img3.close()


def test_quality_and_max_width():
    assert ss._get_screenshot_quality("") == ss.SCREENSHOT_QUALITY
    assert ss._get_screenshot_quality("Code.exe") == min(95, ss.SCREENSHOT_QUALITY + 20)
    assert ss._get_screenshot_quality("chrome.exe") == max(50, ss.SCREENSHOT_QUALITY - 10)
    assert ss._get_screenshot_quality("unknown.exe") == ss.SCREENSHOT_QUALITY
    assert ss._get_screenshot_max_width("") == ss.SCREENSHOT_MAX_WIDTH
    assert ss._get_screenshot_max_width("Code.exe") == min(2560, ss.SCREENSHOT_MAX_WIDTH + 640)
    assert ss._get_screenshot_max_width("chrome.exe") == ss.SCREENSHOT_MAX_WIDTH


def test_get_monitors_cache(monkeypatch):
    fake = FakeSct()
    monkeypatch.setattr(ss, "_mss_instance", fake)
    monkeypatch.setattr(ss, "_monitors_cache", None)
    monkeypatch.setattr(ss, "_monitors_cache_time", 0)
    fake.monitors = [{"left": 0, "top": 0, "width": 2, "height": 2}]
    assert ss._get_monitors() == fake.monitors
    assert ss._get_mss() is fake


def test_take_screenshot_saves_encrypted_and_reuses_duplicate(tmp_path, monkeypatch):
    _reset_globals(monkeypatch)
    monkeypatch.setattr(ss, "SCREENSHOT_DIR", tmp_path)
    fake = FakeSct()
    fake.monitors = [{"left": 0, "top": 0, "width": 2, "height": 2}, {"left": 0, "top": 0, "width": 2, "height": 2}]
    monkeypatch.setattr(ss, "_get_mss", lambda: fake)
    monkeypatch.setattr(ss, "_get_monitors", lambda: fake.monitors)

    fn1, path1, dup1 = ss.take_screenshot(monitor_index=1, app_name="Code.exe")
    assert dup1 is False
    assert Path(path1).exists()
    assert Path(path1).read_bytes()[:4] == b"CDE1"
    assert (tmp_path / fn1).exists()

    fn2, path2, dup2 = ss.take_screenshot(monitor_index=1, app_name="Code.exe")
    assert dup2 is True
    assert fn2 == fn1 and path2 == path1
    # 重复帧不产生第二个文件
    assert len(list(tmp_path.glob("*.jpg"))) == 1


def test_take_screenshot_encryption_failure_no_plaintext(tmp_path, monkeypatch):
    _reset_globals(monkeypatch)
    monkeypatch.setattr(ss, "SCREENSHOT_DIR", tmp_path)
    fake = FakeSct()
    fake.monitors = [{"left": 0, "top": 0, "width": 2, "height": 2}]
    monkeypatch.setattr(ss, "_get_mss", lambda: fake)
    monkeypatch.setattr(ss, "_get_monitors", lambda: fake.monitors)
    monkeypatch.setattr(sc, "save_encrypted_jpeg", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("encrypt down")))

    try:
        ss.take_screenshot(monitor_index=0)
    except RuntimeError as e:
        assert "拒绝明文落盘" in str(e)
    else:
        raise AssertionError("应当抛出 RuntimeError")
    assert list(tmp_path.glob("*.jpg")) == []


def test_encode_image_plaintext_and_encrypted(tmp_path, monkeypatch):
    plain = tmp_path / "plain.jpg"
    plain.write_bytes(b"\xff\xd8plain")
    import base64
    assert base64.b64decode(ss.encode_image_to_base64(str(plain))) == b"\xff\xd8plain"

    enc = tmp_path / "enc.jpg"
    enc.write_bytes(sc.encrypt_bytes(b"\xff\xd8encrypted"))
    assert base64.b64decode(ss.encode_image_to_base64(str(enc))) == b"\xff\xd8encrypted"


def test_encode_image_bad_cipher_returns_empty(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"CDE1" + b"x" * 40)
    assert ss.encode_image_to_base64(str(bad)) == ""


def test_cleanup_and_size(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "SCREENSHOT_DIR", tmp_path)
    old = tmp_path / "old.jpg"
    new = tmp_path / "new.jpg"
    old.write_bytes(b"x")
    new.write_bytes(b"y" * (1024 * 1024))
    old_time = time.time() - 10 * 86400
    import os
    os.utime(old, (old_time, old_time))
    ss.cleanup_screenshots(3)
    assert not old.exists()
    assert new.exists()
    assert ss.get_screenshots_size_mb() > 0
