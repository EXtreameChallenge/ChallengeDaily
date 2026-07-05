"""Final comprehensive smoke test — all API endpoints"""
import json
import urllib.request
import urllib.error
import sys

BASE = "http://127.0.0.1:58888"
TOKEN = open("data/.api_token", encoding="utf-8").read().strip()

total = 0
passed = 0

def api(endpoint, method="GET", data=None, expect_code=200, desc=""):
    global total, passed
    total += 1
    url = f"{BASE}{endpoint}"
    headers = {"X-API-Token": TOKEN, "Content-Type": "application/json; charset=utf-8"}
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    label = desc or f"{method} {endpoint}"
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            actual = resp.getcode()
            rbody = resp.read().decode("utf-8")
            ok = actual == expect_code
            if ok:
                passed += 1
                print(f"  PASS: {label}")
            else:
                print(f"  FAIL: {label} -> {actual} (expected {expect_code})")
            return ok, rbody
    except urllib.error.HTTPError as e:
        actual = e.code
        rbody = e.read().decode("utf-8", errors="replace")
        ok = actual == expect_code
        if ok:
            passed += 1
            print(f"  PASS: {label} -> {actual}")
        else:
            print(f"  FAIL: {label} -> {actual} (expected {expect_code})")
        return ok, rbody
    except Exception as e:
        print(f"  FAIL: {label} -> Exception: {e}")
        return False, ""

print("=" * 60)
print("  ChallengeDaily — Final Comprehensive Smoke Test")
print("=" * 60)

# ── 1. Health & Auth ──
print("\n── 1. Health & Auth ──")
api("/api/health", desc="Health check (with token)")
api("/api/health", method="GET", expect_code=401, desc="Health check (no token)")
# No auth header
_no_auth_req = urllib.request.Request(f"{BASE}/api/health")
try:
    urllib.request.urlopen(_no_auth_req, timeout=5)
    print("  FAIL: No token should get 401")
    total += 1
except urllib.error.HTTPError as e:
    total += 1
    if e.code == 401:
        passed += 1
        print("  PASS: No token -> 401")
    else:
        print(f"  FAIL: No token -> {e.code}")
except:
    total += 1
    print("  FAIL: Connection error")

# ── 2. Status ──
print("\n── 2. Status ──")
api("/api/status", desc="Server status")

# ── 3. Stats ──
print("\n── 3. Statistics ──")
api("/api/stats/today", desc="Today stats")
api("/api/stats/trend?days=7", desc="7-day trend")
api("/api/heatmap?weeks=12", desc="Heatmap 12 weeks")

# ── 4. Activities ──
print("\n── 4. Activities ──")
api("/api/activities?date=2026-07-04", desc="List activities today")
api("/api/activities/search?q=测试", desc="Search activities")
api("/api/activities/categories", desc="Get categories")

# ── 5. Manual Activity CRUD ──
print("\n── 5. Manual Activity CRUD ──")
ok, b = api("/api/activities", "POST",
    {"timestamp": "2026-07-04 16:45:00", "category": "沟通", "summary": "Smoke test activity", "duration_min": 15},
    expect_code=201, desc="Create manual activity")
activity_id = None
if ok:
    try:
        activity_id = json.loads(b).get("activity", {}).get("id") or json.loads(b).get("id")
    except:
        pass

if activity_id:
    api(f"/api/activities/{activity_id}", "PUT",
        {"category": "会议", "summary": "Updated smoke test"},
        desc="Update activity")
    api(f"/api/activities/{activity_id}", "DELETE", desc="Delete activity")
else:
    print("  SKIP: Update/Delete (no activity ID)")

# ── 6. Duplicate timestamp → 409 ──
print("\n── 6. Duplicate timestamp ──")
api("/api/activities", "POST",
    {"timestamp": "2026-07-04 16:50:00", "category": "学习", "summary": "Dup test 1"},
    expect_code=201, desc="First insert")
api("/api/activities", "POST",
    {"timestamp": "2026-07-04 16:50:00", "category": "学习", "summary": "Dup test 2"},
    expect_code=409, desc="Duplicate timestamp -> 409")

# ── 7. Reports ──
print("\n── 7. Reports ──")
for tpl in ["standard", "simple", "technical", "okr"]:
    api(f"/api/report?template={tpl}", desc=f"Generate {tpl} report")

# ── 8. Settings ──
print("\n── 8. Settings ──")
ok, b = api("/api/settings", desc="Get settings")
api("/api/settings", "PUT",
    {"work_start_hour": 8, "work_end_hour": 22},
    desc="Update settings")

# ── 9. Webhooks ──
print("\n── 9. Webhooks ──")
api("/api/webhooks", desc="List webhooks")
# SSRF protection
api("/api/webhooks", "POST",
    {"url": "http://127.0.0.1:9999", "type": "custom"},
    expect_code=400, desc="SSRF block localhost")
api("/api/webhooks", "POST",
    {"url": "http://192.168.0.1/test", "type": "custom"},
    expect_code=400, desc="SSRF block private IP")
# Valid webhook add -> delete
ok, b = api("/api/webhooks", "POST",
    {"url": "https://hooks.example.com/test", "type": "feishu", "name": "Test WH"},
    desc="Add valid webhook")
wh_id = None
if ok:
    try:
        wh_id = json.loads(b).get("webhook", {}).get("id")
    except:
        pass

if wh_id:
    api(f"/api/webhooks/{wh_id}/toggle", "POST", desc="Toggle webhook")
    api(f"/api/webhooks/{wh_id}", "DELETE", desc="Delete webhook")
else:
    print("  SKIP: Toggle/Delete webhook (no webhook ID)")

# ── 10. Auto Report Config ──
print("\n── 10. Auto Report Config ──")
api("/api/auto-report/config", desc="Get auto report config")
api("/api/auto-report/config", "POST",
    {"enabled": False, "auto_time": "18:00"},
    desc="Update auto report config")
api("/api/auto-report/config", "POST",
    {"auto_time": "25:00"},
    expect_code=400, desc="Invalid auto_time 25:00 -> 400")
api("/api/auto-report/config", "POST",
    {"auto_time": "12:99"},
    expect_code=400, desc="Invalid auto_time 12:99 -> 400")

# ── 11. Backup ──
print("\n── 11. Backup ──")
api("/api/backup/info", desc="Backup info")
ok, b = api("/api/backup", "POST", desc="Create backup")

# ── 12. Notifications ──
print("\n── 12. Notifications ──")
api("/api/notifications", desc="Get notifications")

# ── 13. Collector control ──
print("\n── 13. Collector control ──")
api("/api/collector/pause", "POST", desc="Pause collector")
api("/api/status", desc="Status after pause")
api("/api/collector/resume", "POST", desc="Resume collector")
api("/api/status", desc="Status after resume")
api("/api/collector/capture", "POST", desc="Manual capture")

# ── 14. Agent ──
print("\n── 14. Agent ──")
api("/api/agent/auto-report", "POST", desc="Trigger auto report")

# ── 15. SQL injection resistance ──
print("\n── 15. Security ──")
api("/api/activities/search?q='; DROP TABLE activities;--", desc="SQL injection in search")

# ── Summary ──
print("\n" + "=" * 60)
print(f"  RESULT: {passed}/{total} tests passed")
if passed == total:
    print("  ALL TESTS PASSED!")
else:
    print(f"  {total - passed} tests FAILED")
print("=" * 60)
sys.exit(0 if passed == total else 1)
