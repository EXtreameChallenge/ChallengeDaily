"""B46：截图加密链路必须失败关闭，允许旧明文兼容，但绝不静默明文降级。"""
import pytest

import screenshot_crypto as sc


JPEG = b"\xff\xd8\xff\xe0" + b"round12-test" * 8


@pytest.fixture
def crypto_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_get_backend_data_dir", lambda: tmp_path)
    monkeypatch.setattr(sc, "_enc_key", None)
    return tmp_path


@pytest.mark.skipif(not sc.is_encryption_available(), reason="cryptography 不可用")
def test_roundtrip_and_salt_survives_process_restart(crypto_env):
    out = crypto_env / "shot.jpg"
    assert sc.save_encrypted_jpeg(JPEG, str(out)) is True
    assert out.read_bytes()[:4] == b"CDE1"

    salt = crypto_env / sc._SALT_FILE
    assert salt.exists() and len(salt.read_bytes()) == 16

    assert sc.load_and_decrypt(str(out)) == JPEG
    # 模拟进程重启：清空内存密钥，只依赖持久化 salt 重新派生
    sc._enc_key = None
    assert sc.load_and_decrypt(str(out)) == JPEG


def test_salt_backed_up_and_restored_after_loss(crypto_env):
    """B46：盐值必须有备份；主盐值丢失时自动从备份恢复，历史截图不失明。"""
    out = crypto_env / "backup.jpg"
    assert sc.save_encrypted_jpeg(JPEG, str(out)) is True

    salt = crypto_env / sc._SALT_FILE
    original = salt.read_bytes()
    backups = list((crypto_env / "backups" / "salt").glob("screenshot_salt_*.bin"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original

    salt.unlink()
    sc._enc_key = None
    assert sc.load_and_decrypt(str(out)) == JPEG
    assert salt.exists()
    assert salt.read_bytes() == original


def test_privacy_delete_does_not_touch_real_legacy_salt(tmp_path, monkeypatch):
    """B46 根因回归：隔离数据目录下，被遗忘权不得删除真实 APPDATA legacy salt。"""
    import config
    import privacy_data

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    paths = privacy_data._salt_paths()
    assert paths
    assert all(str(tmp_path) in str(p) for p in paths), paths


def test_encryption_unavailable_refuses_plaintext(crypto_env, monkeypatch):
    monkeypatch.setattr(sc, "is_encryption_available", lambda: False)
    out = crypto_env / "must-not-exist.jpg"
    with pytest.raises(sc.EncryptionUnavailableError):
        sc.save_encrypted_jpeg(JPEG, str(out))
    assert not out.exists(), "加密不可用时不得留下明文截图"


def test_key_derivation_failure_refuses_plaintext(crypto_env, monkeypatch):
    monkeypatch.setattr(sc, "_derive_key", lambda: b"")
    out = crypto_env / "must-not-exist-2.jpg"
    with pytest.raises(sc.EncryptionUnavailableError):
        sc.save_encrypted_jpeg(JPEG, str(out))
    assert not out.exists()


@pytest.mark.skipif(not sc.is_encryption_available(), reason="cryptography 不可用")
def test_wrong_salt_raises_instead_of_returning_ciphertext(crypto_env, tmp_path, monkeypatch):
    out = crypto_env / "old-salt.jpg"
    assert sc.save_encrypted_jpeg(JPEG, str(out)) is True
    ciphertext = out.read_bytes()

    other = tmp_path / "other-salt"
    other.mkdir()
    (other / sc._SALT_FILE).write_bytes(b"0123456789abcdef")
    monkeypatch.setattr(sc, "_get_backend_data_dir", lambda: other)
    monkeypatch.setattr(sc, "_enc_key", None)

    with pytest.raises(sc.DecryptionError):
        sc.decrypt_bytes(ciphertext)


def test_legacy_plaintext_is_still_readable():
    plain = b"\xff\xd8\xff\xe0plain-old-jpeg"
    assert sc.decrypt_bytes(plain) == plain


def test_encode_base64_refuses_ciphertext_on_decrypt_failure(tmp_path, monkeypatch):
    import screenshot

    encrypted = sc._MAGIC_HEADER + b"x" * 40
    f = tmp_path / "bad.jpg"
    f.write_bytes(encrypted)

    def boom(_path):
        raise sc.DecryptionError("bad salt")

    monkeypatch.setattr(sc, "load_and_decrypt", boom)
    assert screenshot.encode_image_to_base64(str(f)) == ""
