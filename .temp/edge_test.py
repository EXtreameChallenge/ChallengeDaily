"""Edge case and boundary input test"""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:58888"
TOKEN = open("data/.api_token", encoding="utf-8").read().strip()

def api_call(endpoint, method="GET", data=None, expect_code=200):
    url = f"{BASE}{endpoint}"
    headers = {"X-API-Token": TOKEN, "Content-Type": "application/json; charset=utf-8"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            actual = resp.getcode()
            ok = actual == expect_code
            print(f"  {'PASS' if ok else 'FAIL'}: {method} {endpoint} -> {actual} (expected {expect_code})")
            return True
    except urllib.error.HTTPError as e:
        actual = e.code
        ok = actual == expect_code
        print(f"  {'PASS' if ok else 'FAIL'}: {method} {endpoint} -> {actual} (expected {expect_code})")
        return ok
    except Exception as e:
        print(f"  FAIL: {method} {endpoint} -> Exception: {e}")
        return False

print("=== Edge Case Tests ===\n")

# 1. Invalid date formats
print("1. Invalid date formats:")
api_call("/api/stats/date/abc", expect_code=400)
api_call("/api/stats/date/2024-13-01", expect_code=200)  # nonexistent date but valid format
api_call("/api/stats/date/2024-1-1", expect_code=400)

# 2. Out-of-range values
print("\n2. Out-of-range values:")
api_call("/api/stats/trend?days=0", expect_code=200)  # min 1
api_call("/api/stats/trend?days=100", expect_code=200)  # capped at 30

# 3. Manual activity boundary tests
print("\n3. Manual activity with boundary duration:")
api_call("/api/activities", "POST",
    {"timestamp": "2026-07-04 12:00:00", "category": "开发", "summary": "test", "duration_min": 480},  # max
    expect_code=201)
api_call("/api/activities", "POST",
    {"timestamp": "2026-07-04 12:00:00", "category": "开发", "summary": "test", "duration_min": 0},  # below min, should be clamped to 5
    expect_code=201)
api_call("/api/activities", "POST",
    {"timestamp": "2026-07-04 12:00:00", "category": "开发", "summary": "test", "duration_min": 9999},  # above max, clamped to 480
    expect_code=201)

# 4. Missing required fields
print("\n4. Missing required fields:")
api_call("/api/activities", "POST", {"category": "开发"}, expect_code=400)  # no timestamp
api_call("/api/activities", "POST", {"timestamp": "2026-07-04 12:00:00"}, expect_code=400)  # no category

# 5. Invalid timestamp format
print("\n5. Invalid timestamp format:")
api_call("/api/activities", "POST",
    {"timestamp": "not-a-date", "category": "开发", "summary": "test"},
    expect_code=400)

# 6. LIKE special characters in search
print("\n6. Search with special LIKE characters:")
api_call("/api/activities/search?q=100%25", expect_code=200)  # % sign
api_call("/api/activities/search?q=under_score", expect_code=200)  # _ sign

# 7. SSRF protection
print("\n7. SSRF protection for webhooks:")
api_call("/api/webhooks", "POST",
    {"url": "http://127.0.0.1:8080/test", "type": "custom"},
    expect_code=400)  # should block localhost
api_call("/api/webhooks", "POST",
    {"url": "http://192.168.1.1/test", "type": "custom"},
    expect_code=400)  # should block private IP
api_call("/api/webhooks", "POST",
    {"url": "ftp://example.com/test", "type": "custom"},
    expect_code=400)  # should block non-http

# 8. Empty search query
print("\n8. Empty search query:")
api_call("/api/activities/search?q=", expect_code=200)

# 9. Auto report config validation
print("\n9. Auto report config validation:")
api_call("/api/auto-report/config", "POST", {"auto_time": "not-a-time"}, expect_code=400)
api_call("/api/auto-report/config", "POST", {"auto_time": "25:00"}, expect_code=400)

print("\n=== Edge Case Tests Complete ===")
