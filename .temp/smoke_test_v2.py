"""Final comprehensive smoke test — all API endpoints (corrected)"""
import json
import urllib.request
import urllib.error
import urllib.parse
import sys

BASE = "http://127.0.0.1:58888"
TOKEN = open("data/.api_token", encoding="utf-8").read().strip()

total = 0
passed = 0

def api(endpoint, method="GET", data=None, expect_code=200, desc="", raw=False):
    global total, passed
    total += 1
    url = f"{BASE}{endpoint}"
    headers = {"X-API-Token": TOKEN, "Content-Type": "application/json; charset=utf-8"}
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    label = desc or f"{method} {endpoint}"
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            actual = resp.getcode()
            rbody = resp.read()
            ok = actual == expect_code
            if ok:
                passed += 1
                print(f"  PASS: {label}")
            else:
                print(f"  FAIL: {label} -> {actual} (expected {expect_code})")
            if raw:
                return ok, rbody
            return ok, rbody.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        actual = e.code
        rbody = e.read()
        ok = actual == expect_code
        if ok:
            passed += 1
            print(f"  PASS: {label} -> {actual}")
        else:
            print(f"  FAIL: {label} -> {actual} (expected {expect_code})")
            print(f"    Body: {rbody.decode('utf-8', errors='replace')[:200]}")
        if raw:
            return ok, rbody
        return ok, rbody.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  FAIL: {label} -> Exception: {e}")
        return False, ""

def api_no_auth(endpoint, method="GET", expect_code=401, desc=""):
    global total, passed
    total += 1
    url = f"{BASE}{endpoint}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            actual = resp.getcode()
            ok = actual == expect_code
            if ok:
                passed += 1
                print(f"  PASS: {label}")
            else:
                print(f"  FAIL: {desc} -> {actual} (expected {expect_code})")
    except urllib.error.HTTPError as e:
        actual = e.code
        ok = actual == expect_code
        if ok:
            passed += 1
            print(f"  PASS: {desc} -> {actual}")
        else:
            print(f"  FAIL: {desc} -> {actual} (expected {expect_code})")
    except Exception as e:
        print(f"  FAIL: {desc} -> Exception: {e}")

print("=" * 60)
print("  ChallengeDaily — Final Comprehensive Smoke Test")
print("=" * 60)

# ── 1. Health & Auth ──
print("\n── 1. Health & Auth ──")
api("/api/health", desc="Health check (public)")
api_no_auth("/api/status", expect_code=401, desc="Status without token -> 401")
api_no_auth("/api/activities", expect_code=401, desc="Activities without token -> 401")

# ── 2. Status ──
print("\n── 2. Status ──")
api("/api/status", desc="Server status")

# ── 3. Statistics ──
print("\n── 3. Statistics ──")
api("/api/stats/today", desc="Today stats")
api("/api/stats/trend?days=7", desc="7-day trend")
api("/api/stats/hourly", desc="Hourly stats")
api("/api/stats/rhythm", desc="Work rhythm")

# ── 4. Activities ──
print("\n── 4. Activities ──")
api("/api/activities?date=2026-07-04", desc="List activities today")
# Search with URL-encoded Chinese
q = urllib.parse.quote("测试")
api(f"/api/activities/search?q={q}", desc="Search activities (Chinese)")
# Search with English
api("/api/activities/search?q=test", desc="Search activities (English)")

# ── 5. Timeline & Daily Summary & App Usage ──
print("\n── 5. Timeline, Digest, App Usage ──")
api("/api/timeline?startDate=2026-07-04&endDate=2026-07-04", desc="Timeline")
api("/api/daily-summary?startDate=2026-07-04&endDate=2026-07-04", desc="Daily summary")
api("/api/app-usage?date=2026-07-04", desc="App usage")

# ── 6. Manual Activity CRUD ──
print("\n── 6. Manual Activity CRUD ──")
ok, b = api("/api/activities", "POST",
    {"timestamp": "2026-07-04 17:00:00", "category": "沟通", "summary": "Smoke test CRUD", "duration_min": 10},
    expect_code=201, desc="Create manual activity")
act_id = None
if ok:
    try:
        act_id = json.loads(b).get("activity", {}).get("id") or json.loads(b).get("id")
    except:
        pass

if act_id:
    api(f"/api/activities/{act_id}", "PUT",
        {"category": "会议", "summary": "Updated via smoke test"},
        desc="Update activity")
else:
    print("  SKIP: Update activity (no ID)")

# ── 7. Duplicate timestamp → 409 ──
print("\n── 7. Duplicate timestamp ──")
api("/api/activities", "POST",
    {"timestamp": "2026-07-04 17:05:00", "category": "学习", "summary": "Dup test 1"},
    expect_code=201, desc="First insert OK")
api("/api/activities", "POST",
    {"timestamp": "2026-07-04 17:05:00", "category": "学习", "summary": "Dup test 2"},
    expect_code=409, desc="Duplicate -> 409")

# ── 8. Reports ──
print("\n── 8. Reports ──")
for tpl in ["standard", "simple", "technical", "okr"]:
    api(f"/api/report/daily?template={tpl}", desc=f"Generate {tpl} report")
api("/api/report/daily/content", desc="Get today report content")
api("/api/report?startDate=2026-07-01&endDate=2026-07-04", desc="Report list")

# ── 9. Settings ──
print("\n── 9. Settings ──")
api("/api/settings", desc="Get settings")
api("/api/settings", "POST",
    {"work_start_hour": 8, "work_end_hour": 22},
    desc="Update settings")
# Restore
api("/api/settings", "POST",
    {"work_start_hour": 0, "work_end_hour": 24},
    desc="Restore default settings")

# ── 10. Webhooks ──
print("\n── 10. Webhooks ──")
api("/api/webhooks", desc="List webhooks")
api("/api/webhooks", "POST",
    {"url": "http://127.0.0.1:9999", "type": "custom"},
    expect_code=400, desc="SSRF block localhost")
api("/api/webhooks", "POST",
    {"url": "http://192.168.0.1/test", "type": "custom"},
    expect_code=400, desc="SSRF block private IP")
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
    print("  SKIP: Toggle/Delete webhook")

# ── 11. Auto Report Config ──
print("\n── 11. Auto Report Config ──")
api("/api/auto-report/config", desc="Get config")
api("/api/auto-report/config", "POST",
    {"enabled": False, "auto_time": "18:00"},
    desc="Update config")
api("/api/auto-report/config", "POST",
    {"auto_time": "25:00"},
    expect_code=400, desc="Invalid time 25:00 -> 400")
api("/api/auto-report/config", "POST",
    {"auto_time": "12:99"},
    expect_code=400, desc="Invalid time 12:99 -> 400")

# ── 12. Backup ──
print("\n── 12. Backup ──")
api("/api/backup/info", desc="Backup info")
ok, bdata = api("/api/backup", "POST", desc="Create backup", raw=True)

# ── 13. Notifications ──
print("\n── 13. Notifications ──")
api("/api/notifications", desc="Get notifications")

# ── 14. Collector control ──
print("\n── 14. Collector control ──")
api("/api/collector/pause", "POST", desc="Pause collector")
api("/api/collector/resume", "POST", desc="Resume collector")
api("/api/capture", "POST", desc="Manual capture")

# ── 15. AI test (will fail gracefully without key) ──
print("\n── 15. AI test ──")
api("/api/ai/test", "POST", desc="Test AI connection (should handle gracefully)")

# ── 16. Exports ──
print("\n── 16. Data exports ──")
api("/api/export/activities?startDate=2026-07-04&endDate=2026-07-04", desc="Export activities CSV")
api("/api/export/app-usage?date=2026-07-04", desc="Export app usage CSV")

# ── 17. Security ──
print("\n── 17. Security ──")
# SQL injection via search (URL-encode the special chars)
sqli = urllib.parse.quote("'; DROP TABLE activities;--")
api(f"/api/activities/search?q={sqli}", desc="SQL injection in search (safe)")

# ── Summary ──
print("\n" + "=" * 60)
print(f"  RESULT: {passed}/{total} tests passed")
if passed == total:
    print("  ALL TESTS PASSED!")
else:
    print(f"  {total - passed} tests FAILED")
print("=" * 60)
sys.exit(0 if passed == total else 1)
