"""Windows 系统事件读取 —— 用于校准应用使用时长数据。

通过 PowerShell 的 Get-WinEvent 读取 Windows 事件日志，拿到权威的开关机/登录/注销时间，
作为应用使用时长统计的"应有总时长"基准，能发现"系统在跑但采集器没启动"的漏采时段。

数据源：
  - System log Event ID 12  (Kernel-General)  系统启动
  - System log Event ID 13  (Kernel-General)  系统关闭
  - System log Event ID 41  (Kernel-Power)    意外关机/蓝屏
  - System log Event ID 1   (EventLog)        事件日志服务启动（开机后第一批）
  - Security log Event ID 4624 LogonType=2/11  交互式/解锁登录（需管理员权限，失败时降级）
  - Security log Event ID 4647                 用户发起注销（需管理员权限，失败时降级）
"""

import json
import logging
import subprocess
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger(__name__)

# 事件类型常量
EVENT_BOOT = "boot"          # 开机
EVENT_SHUTDOWN = "shutdown"  # 正常关机
EVENT_CRASH = "crash"        # 意外关机
EVENT_LOGIN = "login"        # 用户登录
EVENT_LOGOFF = "logoff"      # 用户注销

# Windows 事件 ID → 事件类型映射
_SYSTEM_EVENT_MAP = {
    12: EVENT_BOOT,
    13: EVENT_SHUTDOWN,
    41: EVENT_CRASH,
}

# 权威 provider 白名单 —— 同一事件 ID 会被多个 provider 重复发，只信权威源
# - Kernel-General ID 12/13：系统正式启动/关闭事件（最权威）
# - Kernel-Power ID 41：意外断电/蓝屏
# 其他 provider（Wininit、UserModePowerService、EventLog）的 ID 12 是噪音，会重复算
_AUTHORITATIVE_PROVIDERS = {
    "Microsoft-Windows-Kernel-General",
    "Microsoft-Windows-Kernel-Power",
}

# EventLog ID=1 也是开机后第一批事件（事件日志服务启动）
_EVENTLOG_BOOT_ID = 1


def _run_powershell(script: str, timeout: int = 15) -> str:
    """执行 PowerShell 命令并返回 stdout（已去 BOM、去尾部换行）。

    强制 PowerShell 输出 UTF-8，避免 GBK 编码导致中文乱码或 JSON 解析失败。
    使用 CREATE_NO_WINDOW 避免子进程影响父控制台编码。
    """
    # 在脚本开头强制设置输出编码为 UTF-8
    full_script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + script
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", full_script],
        capture_output=True, timeout=timeout, encoding="utf-8", errors="replace",
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    if result.returncode != 0:
        # 不抛异常，让上层降级处理
        logger.debug(f"PowerShell 失败 rc={result.returncode}: {result.stderr.strip()[:200] if result.stderr else ''}")
        return ""
    out = result.stdout or ""
    # 去 BOM
    if out.startswith("\ufeff"):
        out = out[1:]
    return out.strip()


def _parse_ps_datetime(s: str) -> str | None:
    """PowerShell 输出的时间格式 → "%Y-%m-%d %H:%M:%S"。

    输入可能是：
      - "/Date(1783385230000)/"  (旧版 ConvertTo-Json)
      - "2026-07-07T08:39:21.1234567+08:00"  (新版)
      - "2026-07-07 08:39:21"  (已格式化)
    """
    if not s:
        return None
    s = s.strip()
    # /Date(ms)/
    if s.startswith("/Date("):
        try:
            ms = int(s[6:s.index(")")])
            return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            # 截掉时区冒号（+08:00 → +0800）以适配 %z
            s_clean = s
            if fmt.endswith("%z") and len(s) >= 5 and s[-3] == ":":
                s_clean = s[:-3] + s[-2:]
            dt = datetime.strptime(s_clean, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def get_current_boot_time() -> str | None:
    """获取当前系统开机时间（最近一次启动）。

    优先用 WMI/CIM（快且权威），失败时回退到读取最近一条 Event ID 12。
    """
    # CIM 最快：LastBootUpTime
    out = _run_powershell(
        "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')"
    )
    if out and " " in out:
        return out
    # 回退：最近一条 Event ID 12
    out = _run_powershell(
        "(Get-WinEvent -FilterHashtable @{LogName='System'; Id=12} -MaxEvents 1 "
        "-ErrorAction SilentlyContinue).TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')"
    )
    return out if out and " " in out else None


def get_uptime_seconds() -> int:
    """系统已运行时长（秒）。"""
    boot = get_current_boot_time()
    if not boot:
        return 0
    try:
        boot_dt = datetime.strptime(boot, "%Y-%m-%d %H:%M:%S")
        return max(0, int((datetime.now() - boot_dt).total_seconds()))
    except Exception:
        return 0


def get_boot_events(start_date: str, end_date: str) -> list[dict]:
    """读取与 [start_date, end_date] 范围相关的开关机事件。

    返回 [{"timestamp", "event_type", "source"}] 按时间升序。
    - event_type ∈ {boot, shutdown, crash}
    - source 标识来源（System/Kernel-General、System/Kernel-Power、System/EventLog）

    注意：为支持跨天会话，查询范围会向前扩展 30 天，确保能拿到"系统在 start_date 之前开机
    但仍持续运行到查询范围内"的 boot 事件。
    """
    # 向前扩展 30 天，确保能拿到跨天会话的 boot 事件
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        lookback_dt = start_dt - timedelta(days=30)
        lookback = lookback_dt.strftime("%Y-%m-%d")
    except Exception:
        lookback = start_date

    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$start = [datetime]::ParseExact('{lookback}', 'yyyy-MM-dd', $null)
$end = [datetime]::ParseExact('{end_date}', 'yyyy-MM-dd', $null).AddDays(1)
$events = Get-WinEvent -FilterHashtable @{{LogName='System'; Id=12,13,41; StartTime=$start; EndTime=$end}} -ErrorAction SilentlyContinue
if (-not $events) {{ return '[]' }}
$events | Sort-Object TimeCreated | ForEach-Object {{
    [pscustomobject]@{{
        timestamp = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
        event_id = $_.Id
        provider = $_.ProviderName
    }}
}} | ConvertTo-Json -Compress
"""
    out = _run_powershell(script, timeout=20)
    if not out:
        # PowerShell 失败时，用 CIM 当前开机时间兜底
        boot = get_current_boot_time()
        if boot:
            return [{"timestamp": boot, "event_type": EVENT_BOOT, "source": "CIM/Win32_OperatingSystem"}]
        return []
    try:
        # 单条时 PowerShell 不返回数组
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError as e:
        logger.warning(f"解析 PowerShell 输出失败: {e}")
        return []

    result = []
    for ev in data:
        eid = ev.get("event_id")
        etype = _SYSTEM_EVENT_MAP.get(eid)
        if not etype:
            continue
        provider = ev.get("provider", "")
        # 只信权威 provider，过滤掉 Wininit/UserModePowerService 等噪音源
        if provider not in _AUTHORITATIVE_PROVIDERS:
            continue
        result.append({
            "timestamp": ev["timestamp"],
            "event_type": etype,
            "source": f"System/{provider}",
        })

    # 如果查询范围内没有 boot 事件，但当前系统在运行（开机时间 ≤ end_date），
    # 用 CIM 当前开机时间兜底，支持跨天会话
    if not any(r["event_type"] == EVENT_BOOT for r in result):
        boot = get_current_boot_time()
        if boot and boot[:10] <= end_date:
            result.append({
                "timestamp": boot,
                "event_type": EVENT_BOOT,
                "source": "CIM/Win32_OperatingSystem",
            })
    result.sort(key=lambda x: x["timestamp"])
    return result


def get_login_events(start_date: str, end_date: str) -> list[dict]:
    """读取登录/注销事件（需管理员权限，失败返回空列表降级）。

    返回 [{"timestamp", "event_type", "username"}]。
    """
    # Security log 需要管理员权限，普通用户读不到
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$start = [datetime]::ParseExact('{start_date}', 'yyyy-MM-dd', $null)
$end = [datetime]::ParseExact('{end_date}', 'yyyy-MM-dd', $null).AddDays(1)
$login = Get-WinEvent -FilterHashtable @{{LogName='Security'; Id=4624; StartTime=$start; EndTime=$end}} -ErrorAction SilentlyContinue
$logoff = Get-WinEvent -FilterHashtable @{{LogName='Security'; Id=4647; StartTime=$start; EndTime=$end}} -ErrorAction SilentlyContinue
$result = @()
foreach ($e in $login) {{
    $xml = [xml]$e.ToXml()
    $data = $xml.Event.EventData.Data
    $logonType = ($data | Where-Object {{ $_.Name -eq 'LogonType' }}).'#text'
    if ($logonType -in 2, 11) {{
        $result += [pscustomobject]@{{ timestamp=$e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'); event_type='login'; user=($data | Where-Object {{ $_.Name -eq 'TargetUserName' }}).'#text' }}
    }}
}}
foreach ($e in $logoff) {{
    $xml = [xml]$e.ToXml()
    $data = $xml.Event.EventData.Data
    $result += [pscustomobject]@{{ timestamp=$e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'); event_type='logoff'; user=($data | Where-Object {{ $_.Name -eq 'TargetUserName' }}).'#text' }}
}}
$result | Sort-Object timestamp | ConvertTo-Json -Compress
"""
    out = _run_powershell(script, timeout=30)
    if not out:
        return []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "timestamp": d.get("timestamp", ""),
                "event_type": d.get("event_type", ""),
                "username": d.get("user", ""),
            }
            for d in data
        ]
    except json.JSONDecodeError:
        return []


def get_system_sessions(start_date: str, end_date: str) -> list[dict]:
    """合并开关机 + 登录/注销事件，按时间排序成会话段。

    返回 [{"start", "end", "duration_sec", "type", "source"}]：
      - type=boot_session：开机到关机之间的整个时段（截断到查询范围）
      - type=login_session：登录到注销之间的用户会话
    """
    boots = get_boot_events(start_date, end_date)
    logins = get_login_events(start_date, end_date)

    # 查询范围边界：start_date 00:00:00 到 end_date 23:59:59
    range_start = f"{start_date} 00:00:00"
    range_end = f"{end_date} 23:59:59"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 开机会话：从 boot 到下一个 shutdown 或下一个 boot（取早者），或到现在
    # 注意：
    #   - Event ID 41 (crash) 时间戳在 boot 之后但实际表示"上次意外断电"，不作会话分隔
    #   - 如果两个 boot 之间没有 shutdown，说明系统重启了，旧会话结束于新 boot 之前
    sessions = []
    for i, ev in enumerate(boots):
        if ev["event_type"] != EVENT_BOOT:
            continue
        raw_start = ev["timestamp"]
        # 找下一个 shutdown 或下一个 boot（取早者），跳过紧随 boot 的 crash
        raw_end = None
        for j in range(i + 1, len(boots)):
            nxt = boots[j]
            if nxt["event_type"] == EVENT_SHUTDOWN:
                raw_end = nxt["timestamp"]
                break
            if nxt["event_type"] == EVENT_BOOT:
                # 遇到下一个 boot 说明系统重启了，旧会话结束
                raw_end = nxt["timestamp"]
                break
            # crash 跳过（时间戳在 boot 之后，是延迟记录的上次意外断电）
        if not raw_end:
            # 仍然在运行
            raw_end = now_str

        # 截断到查询范围
        start = raw_start if raw_start > range_start else range_start
        end = raw_end if raw_end < range_end else range_end
        # 如果完全在范围外（开机晚于 range_end 或关机早于 range_start），跳过
        if start > range_end or end < range_start:
            continue
        try:
            duration = int((datetime.strptime(end, "%Y-%m-%d %H:%M:%S") -
                            datetime.strptime(start, "%Y-%m-%d %H:%M:%S")).total_seconds())
        except Exception:
            duration = 0
        sessions.append({
            "start": start,
            "end": end,
            "raw_start": raw_start,
            "raw_end": raw_end,
            "duration_sec": max(0, duration),
            "type": "boot_session",
            "source": ev["source"],
            "truncated_start": raw_start < range_start,  # 标记是否被截断（跨天会话）
            "truncated_end": raw_end > range_end,
        })

    # 登录会话（可选，权限不足时为空）
    for i, ev in enumerate(logins):
        if ev["event_type"] != EVENT_LOGIN:
            continue
        raw_start = ev["timestamp"]
        raw_end = None
        for j in range(i + 1, len(logins)):
            if logins[j]["event_type"] == EVENT_LOGOFF:
                raw_end = logins[j]["timestamp"]
                break
        if not raw_end:
            raw_end = now_str
        start = raw_start if raw_start > range_start else range_start
        end = raw_end if raw_end < range_end else range_end
        if start > range_end or end < range_start:
            continue
        try:
            duration = int((datetime.strptime(end, "%Y-%m-%d %H:%M:%S") -
                            datetime.strptime(start, "%Y-%m-%d %H:%M:%S")).total_seconds())
        except Exception:
            duration = 0
        sessions.append({
            "start": start,
            "end": end,
            "raw_start": raw_start,
            "raw_end": raw_end,
            "duration_sec": max(0, duration),
            "type": "login_session",
            "source": f"Security/{ev.get('username', '')}",
            "truncated_start": raw_start < range_start,
            "truncated_end": raw_end > range_end,
        })

    sessions.sort(key=lambda x: x["start"])
    return sessions


@lru_cache(maxsize=4)
def _cached_boot_events(start_date: str, end_date: str) -> tuple:
    """5 分钟内的缓存，避免反复跑 PowerShell。返回 tuple 使其可 hash。"""
    events = get_boot_events(start_date, end_date)
    return tuple(tuple(d.items()) for d in events)


def get_system_coverage(start_date: str, end_date: str) -> dict:
    """计算指定日期范围内系统"应有运行时长"。

    返回：
      {
        "total_uptime_sec": int,        # 系统开机总时长（截断到查询范围）
        "total_uptime_min": float,
        "sessions": [...],              # 会话段列表
        "boot_count": int,              # 查询范围内开机次数
        "shutdown_count": int,          # 查询范围内关机次数
        "crash_count": int,             # 查询范围内意外关机次数
        "current_uptime_sec": int,      # 当前系统已运行时长（用于"还在运行"展示）
      }
    """
    sessions = get_system_sessions(start_date, end_date)
    boot_sessions = [s for s in sessions if s["type"] == "boot_session"]
    total_uptime = sum(s["duration_sec"] for s in boot_sessions)

    # 只统计查询范围内的事件
    events = get_boot_events(start_date, end_date)
    range_start_str = f"{start_date} 00:00:00"
    range_end_str = f"{end_date} 23:59:59"
    in_range_events = [e for e in events if range_start_str <= e["timestamp"] <= range_end_str]

    return {
        "total_uptime_sec": total_uptime,
        "total_uptime_min": round(total_uptime / 60, 1),
        "sessions": boot_sessions,
        "boot_count": sum(1 for e in in_range_events if e["event_type"] == EVENT_BOOT),
        "shutdown_count": sum(1 for e in in_range_events if e["event_type"] == EVENT_SHUTDOWN),
        "crash_count": sum(1 for e in in_range_events if e["event_type"] == EVENT_CRASH),
        "current_uptime_sec": get_uptime_seconds(),
    }


if __name__ == "__main__":
    # 自测：打印今天的系统事件
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== 系统事件 {today} ===")
    print("当前开机时间:", get_current_boot_time())
    print("已运行时长:", get_uptime_seconds(), "秒")
    print()
    print("--- 开关机事件 ---")
    for ev in get_boot_events(today, today):
        print(f"  {ev['timestamp']}  {ev['event_type']:8s}  {ev['source']}")
    print()
    print("--- 会话段 ---")
    for s in get_system_sessions(today, today):
        print(f"  {s['start']} → {s['end']}  ({s['duration_sec']}s)  {s['type']}")
    print()
    print("--- 覆盖率 ---")
    cov = get_system_coverage(today, today)
    print(f"  总开机时长: {cov['total_uptime_min']} 分钟")
    print(f"  开机/关机/崩溃: {cov['boot_count']}/{cov['shutdown_count']}/{cov['crash_count']}")
