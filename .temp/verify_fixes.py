"""Verify BUG #3 and BUG #4 fixes after backend restart"""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:58888"
TOKEN = open("data/.api_token", encoding="utf-8").read().strip()

def api_call(endpoint, method="GET", data=None, expect_code=200):
    url = f"{BASE}{endpoint}"
    headers = {"X-API-Token": TOKEN, "Content-Type": "application/json; charset=utf-8"}
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            actual = resp.getcode()
            body_text = resp.read().decode("utf-8")
            ok = actual == expect_code
            print(f"  {'PASS' if ok else 'FAIL'}: {method} {endpoint} -> {actual} (expected {expect_code})")
            if not ok:
                print(f"    Body: {body_text[:200]}")
            return ok, body_text
    except urllib.error.HTTPError as e:
        actual = e.code
        body_text = e.read().decode("utf-8", errors="replace")
        ok = actual == expect_code
        print(f"  {'PASS' if ok else 'FAIL'}: {method} {endpoint} -> {actual} (expected {expect_code})")
        if not ok:
            print(f"    Body: {body_text[:200]}")
        return ok, body_text
    except Exception as e:
        print(f"  FAIL: {method} {endpoint} -> Exception: {e}")
        return False, ""

results = []

print("=== BUG #3: Duplicate timestamp manual activity -> 409 ===")
ts = "2026-07-04 14:33:00"
# First insert should succeed
r, b = api_call("/api/activities", "POST",
    {"timestamp": ts, "category": "开发", "summary": "BUG3 test first"}, expect_code=201)
results.append(r)
# Second insert with same timestamp should return 409
r, b = api_call("/api/activities", "POST",
    {"timestamp": ts, "category": "开发", "summary": "BUG3 test duplicate"}, expect_code=409)
results.append(r)
if "已存在" in b or "重复" in b or "冲突" in b:
    print("  PASS: Error message is user-friendly (mentions existing/duplicate/conflict)")
else:
    print(f"  WARN: Error message may not be user-friendly: {b[:100]}")

print("\n=== BUG #4: auto_time 25:00 -> 400 ===")
r, b = api_call("/api/auto-report/config", "POST",
    {"auto_time": "25:00"}, expect_code=400)
results.append(r)
if "0-23" in b or "无效" in b:
    print("  PASS: Error message mentions valid range")
else:
    print(f"  WARN: Error message: {b[:100]}")

# Also test other invalid times
r, b = api_call("/api/auto-report/config", "POST",
    {"auto_time": "12:99"}, expect_code=400)
results.append(r)

print("\n=== Search fix verification ===")
r, b = api_call("/api/activities/search?q=BUG3", expect_code=200)
results.append(r)
try:
    data = json.loads(b)
    count = len(data.get("activities", []))
    print(f"  Found {count} results for 'BUG3'")
except:
    print(f"  WARN: Could not parse search response")

print(f"\n=== Results: {sum(results)}/{len(results)} passed ===")
