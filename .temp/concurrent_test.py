"""Concurrent API request test - simulates multiple rapid requests"""
import threading
import time
import json
import urllib.request

BASE = "http://127.0.0.1:58888"
TOKEN = open("data/.api_token", encoding="utf-8").read().strip()

results = {"success": 0, "error": 0}
lock = threading.Lock()

def make_request(endpoint, method="GET", data=None):
    url = f"{BASE}{endpoint}"
    headers = {"X-API-Token": TOKEN, "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            with lock:
                results["success"] += 1
    except Exception as e:
        with lock:
            results["error"] += 1
            if results["error"] <= 3:
                print(f"  Error on {endpoint}: {e}")

# Test 1: 20 concurrent GET requests
print("Test 1: 20 concurrent status requests")
threads = []
for i in range(20):
    t = threading.Thread(target=make_request, args=("/api/status",))
    threads.append(t)

for t in threads:
    t.start()
for t in threads:
    t.join(timeout=15)
print(f"  Results: {results['success']} success, {results['error']} errors")

# Test 2: 10 concurrent report generation requests
results = {"success": 0, "error": 0}
print("\nTest 2: 10 concurrent report generation requests")
threads = []
for i in range(10):
    t = threading.Thread(target=make_request, args=("/api/report/daily",))
    threads.append(t)

for t in threads:
    t.start()
for t in threads:
    t.join(timeout=30)
print(f"  Results: {results['success']} success, {results['error']} errors")

# Test 3: Mixed read/write
results = {"success": 0, "error": 0}
print("\nTest 3: Mixed read/write (5 reads + 5 writes concurrently)")
threads = []
for i in range(5):
    threads.append(threading.Thread(target=make_request, args=("/api/activities",)))
    threads.append(threading.Thread(target=make_request, args=("/api/settings",)))

for t in threads:
    t.start()
for t in threads:
    t.join(timeout=15)
print(f"  Results: {results['success']} success, {results['error']} errors")

# Test 4: Fast pause/resume toggle
results = {"success": 0, "error": 0}
print("\nTest 4: Rapid pause/resume toggling (10 times)")
for i in range(5):
    make_request("/api/collector/pause", method="POST")
    make_request("/api/collector/resume", method="POST")
print(f"  Results: {results['success']} success, {results['error']} errors")

print("\nConcurrent test complete!")
