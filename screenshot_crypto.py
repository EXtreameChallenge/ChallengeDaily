"""
P17-1: 截图 AES-256-GCM 加密存储
防止截图文件被直接打开查看，即使 .db 文件和截图目录被窃取也无法还原画面。

设计：
  - 密钥派生：从用户机器 ID + 安装时随机盐 → PBKDF2-HMAC-SHA256 → 32 字节 AES 密钥
  - 加密算法：AES-256-GCM（带认证标签，防篡改）
  - 文件格式：[4B MAGIC][12B nonce][密文+16B auth_tag]
  - 向后兼容：无 MAGIC 头的旧 .jpg 明文仍可读取；加密失败绝不回退明文（B46 失败关闭）
  - 解密时机：仅在 AI 分析或用户查看时临时解密到内存，不落盘

依赖：cryptography 库（已在 requirements 中）
"""
import os
import sys
import base64
import hashlib
import logging
import shutil
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
_SALT_BACKUP_DIR = "salt"  # 盐值备份目录（backend-data/backups/salt）
_SALT_BACKUP_KEEP = 5  # 最多保留 5 代盐值备份
_KEY_LEN = 32  # AES-256 需要 32 字节密钥

# 加密标识头（用于判断文件是否已加密）
_MAGIC_HEADER = b"CDE1"  # ChallengeDaily Encrypted v1


class EncryptionUnavailableError(RuntimeError):
    """加密能力不可用或密钥派生失败；调用方必须拒绝明文落盘。"""


class DecryptionError(RuntimeError):
    """密文存在但无法解密；调用方不得把密文当明文继续使用。"""


def _legacy_backend_data_dir() -> Path:
    """轮10 前的盐值目录（仅用于一次性搬移旧盐值）。"""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        return Path(base) / 'challenge-daily' / 'backend-data'
    return Path.home() / '.challenge-daily' / 'backend-data'


def _get_backend_data_dir() -> Path:
    """轮10 统一：盐值与主库都在 config.DATA_DIR。"""
    from config import DATA_DIR
    return Path(DATA_DIR)


def _migrate_legacy_salt(salt_path: Path) -> None:
    """旧安装盐值在 APPDATA；首次使用时复制到统一数据目录，保留原文件做只读归档。"""
    if salt_path.exists():
        return
    legacy = _legacy_backend_data_dir() / _SALT_FILE
    if legacy.exists() and legacy.resolve() != salt_path.resolve():
        try:
            salt_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, salt_path)
            logger.info(f"盐值已迁移到统一数据目录: {salt_path}")
        except Exception as e:
            logger.warning(f"盐值迁移失败: {e}")


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


def _salt_backup_dir() -> Path:
    """盐值备份目录；salt 文件丢失时优先从这里恢复，避免历史截图集体失明。"""
    return _get_backend_data_dir() / "backups" / _SALT_BACKUP_DIR


def _backup_salt(salt: bytes) -> None:
    """按内容哈希备份盐值，最多保留最近 5 代；重复盐值不重复写。"""
    if len(salt) != 16:
        return
    try:
        backup_dir = _salt_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(salt).hexdigest()[:16]
        target = backup_dir / f"screenshot_salt_{digest}.bin"
        if not target.exists():
            target.write_bytes(salt)
            logger.info(f"截图盐值已备份: {target}")
        backups = sorted(
            backup_dir.glob("screenshot_salt_*.bin"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[_SALT_BACKUP_KEEP:]:
            old.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"截图盐值备份失败（不影响主盐值）: {e}")


def _restore_salt_from_backup() -> Optional[bytes]:
    """主盐值缺失时，按修改时间从备份中恢复最近一代。"""
    backup_dir = _salt_backup_dir()
    if not backup_dir.exists():
        return None
    backups = sorted(
        backup_dir.glob("screenshot_salt_*.bin"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for backup in backups:
        try:
            salt = backup.read_bytes()
            if len(salt) != 16:
                continue
            salt_path = _get_backend_data_dir() / _SALT_FILE
            salt_path.parent.mkdir(parents=True, exist_ok=True)
            salt_path.write_bytes(salt)
            logger.warning(f"主截图盐值缺失，已从备份恢复: {backup} -> {salt_path}")
            return salt
        except Exception as e:
            logger.warning(f"从备份恢复截图盐值失败 {backup}: {e}")
    return None


def _get_or_create_salt() -> bytes:
    """获取或创建盐值文件（16 字节随机盐）"""
    salt_path = _get_backend_data_dir() / _SALT_FILE
    _migrate_legacy_salt(salt_path)
    if salt_path.exists():
        salt = salt_path.read_bytes()
        _backup_salt(salt)
        return salt
    restored = _restore_salt_from_backup()
    if restored is not None:
        return restored
    # 首次创建
    salt = os.urandom(16)
    salt_path.parent.mkdir(parents=True, exist_ok=True)
    salt_path.write_bytes(salt)
    _backup_salt(salt)
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
    B46: 加密不可用时抛错，绝不返回明文；调用方必须失败关闭。
    """
    if not is_encryption_available():
        raise EncryptionUnavailableError("cryptography 不可用，拒绝明文降级")

    key = _derive_key()
    if not key:
        raise EncryptionUnavailableError("截图加密密钥派生失败，拒绝明文降级")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)  # GCM 推荐 12 字节 nonce
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return _MAGIC_HEADER + nonce + ciphertext
    except Exception as e:
        logger.error(f"加密失败: {e}")
        raise EncryptionUnavailableError(f"加密失败，拒绝明文降级: {e}") from e


def decrypt_bytes(data: bytes) -> bytes:
    """解密字节数据

    自动识别加密文件（MAGIC 头）和明文文件（向后兼容）。
    B46: 密文解密失败必须抛错，绝不能把密文当明文返回。
    """
    # 检查是否为加密文件
    if len(data) < len(_MAGIC_HEADER) + 12 + 16:
        return data  # 太短，肯定是明文

    if data[:4] != _MAGIC_HEADER:
        return data  # 明文文件，原样返回（旧数据兼容）

    if not is_encryption_available():
        raise DecryptionError("文件已加密但 cryptography 库不可用，无法解密")

    key = _derive_key()
    if not key:
        raise DecryptionError("截图解密密钥派生失败")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = data[4:16]  # 12 字节 nonce
        ciphertext = data[16:]  # 密文 + auth_tag
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        logger.error(f"解密失败: {e}")
        raise DecryptionError(f"截图解密失败（salt 或机器密钥不匹配）: {e}") from e


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

    B46: 加密失败时删除半成品并抛错，绝不写明文兜底。
    """
    target = Path(filepath)
    try:
        encrypted = encrypt_bytes(img_bytes)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'wb') as f:
            f.write(encrypted)
        return True
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        raise


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
        raise


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
