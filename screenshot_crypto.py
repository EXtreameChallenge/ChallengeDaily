"""
P17-1: 截图 AES-256-GCM 加密存储
防止截图文件被直接打开查看，即使 .db 文件和截图目录被窃取也无法还原画面。

设计：
  - 密钥派生：从用户机器 ID + 安装时随机盐 → PBKDF2-HMAC-SHA256 → 32 字节 AES 密钥
  - 加密算法：AES-256-GCM（带认证标签，防篡改）
  - 文件格式：[16B IV][16B auth_tag][密文...]，扩展名 .enc.jpg
  - 向后兼容：老的 .jpg 文件仍可读取（透明解密失败时回退到明文）
  - 解密时机：仅在 AI 分析或用户查看时临时解密到内存，不落盘

依赖：cryptography 库（已在 requirements 中）
"""
import os
import sys
import base64
import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 加密密钥缓存（进程级单例）
_enc_key: Optional[bytes] = None
_key_lock = threading.Lock()

# 密钥派生参数
_PBKDF2_ITERATIONS = 100_000  # 迭代次数，约 100ms 派生时间
_SALT_FILE = "screenshot_salt.bin"  # 盐值文件名（存于 backend-data 目录）
_KEY_LEN = 32  # AES-256 需要 32 字节密钥

# 加密标识头（用于判断文件是否已加密）
_MAGIC_HEADER = b"CDE1"  # ChallengeDaily Encrypted v1


def _get_backend_data_dir() -> Path:
    """获取后端数据目录（与 db.py 一致）"""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        return Path(base) / 'challenge-daily' / 'backend-data'
    return Path.home() / '.challenge-daily' / 'backend-data'


def _get_machine_id() -> str:
    """获取机器唯一标识（Windows: MachineGuid，其他: hostname）"""
    try:
        if sys.platform == 'win32':
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\\Microsoft\\Cryptography"
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                return str(guid)
        else:
            import socket
            return socket.gethostname()
    except Exception as e:
        logger.warning(f"获取机器ID失败: {e}")
    # 安全回退：生成随机 ID 并持久化到文件，保证每台机器不同
    fallback_path = _get_backend_data_dir() / "machine_fallback_id.bin"
    if fallback_path.exists():
        try:
            return fallback_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    fallback_id = os.urandom(32).hex()
    try:
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(fallback_id, encoding="utf-8")
        logger.info(f"已生成并保存随机机器ID回退值")
    except Exception as save_err:
        logger.warning(f"保存随机机器ID失败: {save_err}")
    return fallback_id


def _get_or_create_salt() -> bytes:
    """获取或创建盐值文件（16 字节随机盐）"""
    salt_path = _get_backend_data_dir() / _SALT_FILE
    if salt_path.exists():
        return salt_path.read_bytes()
    # 首次创建
    salt = os.urandom(16)
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    salt_path.write_bytes(salt)
    return salt


def _derive_key() -> bytes:
    """PBKDF2 派生 AES-256 密钥（机器 ID + 盐值）"""
    with _key_lock:
        global _enc_key
        if _enc_key is not None:
            return _enc_key

        try:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes

            machine_id = _get_machine_id()
            salt = _get_or_create_salt()

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=_KEY_LEN,
                salt=salt,
                iterations=_PBKDF2_ITERATIONS,
            )
            _enc_key = kdf.derive(machine_id.encode('utf-8'))
            logger.info("截图加密密钥派生成功")
            return _enc_key
        except ImportError:
            logger.warning("cryptography 库未安装，截图加密功能不可用")
            _enc_key = b''  # 标记为不可用
            return _enc_key
        except Exception as e:
            logger.error(f"密钥派生失败: {e}")
            _enc_key = b''
            return _enc_key


def is_encryption_available() -> bool:
    """检查加密功能是否可用（cryptography 库已安装）"""
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


def encrypt_bytes(data: bytes) -> bytes:
    """加密字节数据

    返回格式: [4B MAGIC][12B nonce][密文+16B auth_tag]
    失败时返回原始数据（降级为明文，保证可用性）
    """
    if not is_encryption_available():
        return data

    key = _derive_key()
    if not key:
        return data

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)  # GCM 推荐 12 字节 nonce
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return _MAGIC_HEADER + nonce + ciphertext
    except Exception as e:
        logger.error(f"加密失败: {e}")
        return data


def decrypt_bytes(data: bytes) -> bytes:
    """解密字节数据

    自动识别加密文件（MAGIC 头）和明文文件（向后兼容）。
    失败时返回原始数据（可能是明文，降级保证可用性）
    """
    # 检查是否为加密文件
    if len(data) < len(_MAGIC_HEADER) + 12 + 16:
        return data  # 太短，肯定是明文

    if data[:4] != _MAGIC_HEADER:
        return data  # 明文文件，原样返回

    if not is_encryption_available():
        logger.warning("文件已加密但 cryptography 库不可用，无法解密")
        return data

    key = _derive_key()
    if not key:
        return data

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = data[4:16]  # 12 字节 nonce
        ciphertext = data[16:]  # 密文 + auth_tag
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        logger.error(f"解密失败: {e}")
        return data


def is_encrypted_file(filepath: str) -> bool:
    """判断文件是否为加密格式"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
        return header == _MAGIC_HEADER
    except Exception:
        return False


def save_encrypted_jpeg(img_bytes: bytes, filepath: str) -> bool:
    """将 JPEG 字节数据加密后保存到文件

    Args:
        img_bytes: 原始 JPEG 字节数据
        filepath: 目标文件路径

    Returns:
        True 表示已加密保存，False 表示降级为明文保存
    """
    try:
        encrypted = encrypt_bytes(img_bytes)
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(encrypted)
        return encrypted[:4] == _MAGIC_HEADER
    except Exception as e:
        logger.error(f"加密保存失败，降级明文: {e}")
        try:
            with open(filepath, 'wb') as f:
                f.write(img_bytes)
        except Exception as e2:
            logger.error(f"明文保存也失败: {e2}")
        return False


def load_and_decrypt(filepath: str) -> bytes:
    """加载文件并自动解密

    用于 AI 分析或前端预览时读取截图内容。
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        return decrypt_bytes(data)
    except Exception as e:
        logger.error(f"读取文件失败: {filepath}: {e}")
        return b''


# ── 迁移工具：批量加密已有截图 ──

def migrate_existing_screenshots() -> dict:
    """批量加密已有截图文件（仅加密明文 .jpg 文件）

    返回: {"total": int, "encrypted": int, "skipped": int, "failed": int}
    """
    from config import SCREENSHOT_DIR

    result = {"total": 0, "encrypted": 0, "skipped": 0, "failed": 0}

    if not is_encryption_available():
        result["failed"] = -1
        return result

    if not SCREENSHOT_DIR.exists():
        return result

    for f in SCREENSHOT_DIR.iterdir():
        if not f.is_file() or not f.name.lower().endswith('.jpg'):
            continue
        result["total"] += 1

        # 跳过已加密的文件
        if is_encrypted_file(str(f)):
            result["skipped"] += 1
            continue

        try:
            with open(f, 'rb') as fp:
                data = fp.read()
            encrypted = encrypt_bytes(data)
            if encrypted[:4] == _MAGIC_HEADER:
                # 原子写入：先写临时文件再重命名
                tmp_path = f.with_suffix('.enc.tmp')
                with open(tmp_path, 'wb') as fp:
                    fp.write(encrypted)
                tmp_path.replace(f)
                result["encrypted"] += 1
            else:
                result["skipped"] += 1
        except Exception as e:
            logger.error(f"迁移加密失败 {f.name}: {e}")
            result["failed"] += 1

    return result
