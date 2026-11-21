"""
ChallengeDaily Windows 版 — 敏感数据加密模块
使用 Windows DPAPI (Data Protection API) 加密 API Key 等敏感信息
DPAPI 使用 Windows 用户登录凭据加密，无需额外密码管理
"""
import ctypes
import ctypes.wintypes
import base64
import json
import logging
from pathlib import Path
from config import DATA_DIR
from file_utils import atomic_write_bytes, backup_file

logger = logging.getLogger(__name__)

# ── DPAPI 常量 ──
CRYPTPROTECT_UI_FORBIDDEN = 0x01

# ── Windows API 声明 ──
_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32

class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _dpapi_encrypt(data: bytes) -> bytes:
    """使用 DPAPI 加密字节数据"""
    input_blob = DATA_BLOB()
    input_blob.cbData = len(data)
    input_blob.pbData = (ctypes.c_ubyte * len(data))(*data)

    output_blob = DATA_BLOB()

    if not _crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,  # 描述（可选）
        None,  # 可选熵
        None,  # 保留
        None,  # 提示结构
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise OSError("DPAPI encrypt failed")

    try:
        encrypted = (ctypes.c_ubyte * output_blob.cbData)()
        ctypes.memmove(encrypted, output_blob.pbData, output_blob.cbData)
        return bytes(encrypted)
    finally:
        _kernel32.LocalFree(output_blob.pbData)


def _dpapi_decrypt(data: bytes) -> bytes:
    """使用 DPAPI 解密字节数据"""
    input_blob = DATA_BLOB()
    input_blob.cbData = len(data)
    input_blob.pbData = (ctypes.c_ubyte * len(data))(*data)

    output_blob = DATA_BLOB()

    if not _crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,  # 描述输出
        None,  # 可选熵
        None,  # 保留
        None,  # 提示结构
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise OSError("DPAPI decrypt failed")

    try:
        decrypted = (ctypes.c_ubyte * output_blob.cbData)()
        ctypes.memmove(decrypted, output_blob.pbData, output_blob.cbData)
        return bytes(decrypted)
    finally:
        _kernel32.LocalFree(output_blob.pbData)


# ── 加密存储文件路径 ──
_VAULT_PATH = DATA_DIR / "vault.dat"


def save_secret(key: str, value: str) -> None:
    """
    加密保存一个密钥值对到本地 vault 文件。
    key: 键名（如 'ai_api_key'）
    value: 明文值
    """
    # 读取现有 vault
    vault = _load_vault()
    vault[key] = value

    # 序列化 + 加密
    plaintext = json.dumps(vault, ensure_ascii=False).encode("utf-8")
    encrypted = _dpapi_encrypt(plaintext)
    encoded = base64.b64encode(encrypted)

    # 原子写入：先备份，再写临时文件后替换
    if _VAULT_PATH.exists():
        backup_file(_VAULT_PATH)
    atomic_write_bytes(_VAULT_PATH, encoded)
    logger.debug(f"Secret saved: {key}")


def load_secret(key: str, default: str = "") -> str:
    """
    从加密 vault 读取一个密钥值。
    key: 键名
    default: 不存在时的默认值
    """
    vault = _load_vault()
    return vault.get(key, default)


def delete_secret(key: str) -> None:
    """从加密 vault 删除一个密钥"""
    vault = _load_vault()
    if key in vault:
        del vault[key]
        plaintext = json.dumps(vault, ensure_ascii=False).encode("utf-8")
        encrypted = _dpapi_encrypt(plaintext)
        encoded = base64.b64encode(encrypted)
        backup_file(_VAULT_PATH)
        atomic_write_bytes(_VAULT_PATH, encoded)


def _load_vault() -> dict:
    """读取整个 vault 字典"""
    if not _VAULT_PATH.exists():
        return {}

    try:
        encoded = _VAULT_PATH.read_bytes()
        encrypted = base64.b64decode(encoded)
        plaintext = _dpapi_decrypt(encrypted)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to load vault: {e}")
        # 损坏文件重命名保留，避免 save_secret 后覆盖性删除
        corrupt_path = _VAULT_PATH.with_suffix(".corrupt")
        try:
            _VAULT_PATH.rename(corrupt_path)
            logger.warning(f"Vault 损坏，已备份为: {corrupt_path}")
        except Exception:
            pass
        return {}


def has_vault() -> bool:
    """检查 vault 文件是否存在"""
    return _VAULT_PATH.exists()
