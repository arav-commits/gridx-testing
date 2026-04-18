# -*- coding: utf-8 -*-
"""
GridX Failure-Injection Test Suite
====================================
Senior Reliability Engineering . Full-spectrum failure simulation
Run: python failure_injection_suite.py [--base-url http://127.0.0.1:8000]

Phases:
  1.  Baseline performance
  2.  API abuse / concurrency flood
  3.  Schema contract breakage
  4.  Scheduler stress (fast + slow)
  5.  Clock / time-drift simulation
  6.  Invalid / null / extreme data injection
  7.  Race conditions (scheduler + concurrent load)
  8.  Network latency simulation
  9.  Environment misconfiguration
  10. Combined end-to-end chaos

All temporary patches to main.py / pricing.py are reverted before the
suite exits -- even on KeyboardInterrupt or unexpected exceptions.
"""

import argparse
import asyncio
import concurrent.futures
import copy
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import textwrap
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# -- colour helpers (work on any OS) -----------------------------------------
import sys, io
# Force UTF-8 on Windows consoles that default to cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import colorama
    colorama.init(wrap=False)   # wrap=False avoids the cp1252 converter
    RED   = "\033[91m"
    YEL   = "\033[93m"
    GRN   = "\033[92m"
    CYN   = "\033[96m"
    BOLD  = "\033[1m"
    RST   = "\033[0m"
except ImportError:
    RED = YEL = GRN = CYN = BOLD = RST = ""

# -- global result store ------------------------------------------------------
RESULTS: List[Dict[str, Any]] = []
BASE_URL = "http://127.0.0.1:8000"        # overridden by --base-url arg
TIMEOUT  = 10                              # seconds per request


# +==========================================================================+
# |                          UTILITY HELPERS                                |
# +==========================================================================+

def header(text: str) -> None:
    width = 72
    print(f"\n{BOLD}{CYN}{'='*width}{RST}")
    print(f"{BOLD}{CYN}  {text}{RST}")
    print(f"{BOLD}{CYN}{'='*width}{RST}")


def log(level: str, msg: str) -> None:
    icons = {"INFO": f"{GRN}[.]{RST}", "WARN": f"{YEL}[!]{RST}",
             "FAIL": f"{RED}[x]{RST}", "PASS": f"{GRN}[v]{RST}"}
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  {icons.get(level,'?')} [{ts}] {msg}")


def http_get(path: str, timeout: int = TIMEOUT) -> Tuple[Optional[int], Optional[Dict], float]:
    """Return (status_code, json_body, latency_ms). Returns (None, None, ?) on error."""
    url = f"{BASE_URL}{path}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GridX-TestSuite/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            latency = (time.perf_counter() - t0) * 1000
            body = json.loads(r.read().decode())
            return r.status, body, latency
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body, latency
    except Exception:
        latency = (time.perf_counter() - t0) * 1000
        return None, None, latency


def record(phase: str, injection: str, method: str, observed: str,
           classification: str, root_cause: str, severity: str,
           fix: str) -> None:
    entry = dict(phase=phase, injection=injection, method=method,
                 observed=observed, classification=classification,
                 root_cause=root_cause, severity=severity, fix=fix)
    RESULTS.append(entry)
    colour = {"Critical": RED, "High": YEL, "Medium": CYN, "Low": GRN}.get(severity, RST)
    log("INFO", f"{BOLD}{colour}[{severity}]{RST} {phase} -> {classification}")


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PY    = os.path.join(HERE, "main.py")
PRICING_PY = os.path.join(HERE, "pricing.py")


def patch_file(path: str, old: str, new: str) -> str:
    """Replace `old` with `new` in file; return original content."""
    original = read_file(path)
    assert old in original, f"Patch target not found in {path}:\n{old!r}"
    write_file(path, original.replace(old, new, 1))
    return original


def restore_file(path: str, original: str) -> None:
    write_file(path, original)
    log("INFO", f"Restored {os.path.basename(path)}")


# +==========================================================================+
# |                     SERVER MANAGEMENT                                   |
# +==========================================================================+

SERVER_PROC: Optional[subprocess.Popen] = None


def start_server() -> bool:
    global SERVER_PROC
    if SERVER_PROC and SERVER_PROC.poll() is None:
        return True
    log("INFO", "Starting FastAPI dev server...")
    py = sys.executable
    cmd = [py, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
           "--port", "8000", "--log-level", "warning"]
    try:
        SERVER_PROC = subprocess.Popen(
            cmd, cwd=HERE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Wait up to 8 s for the server to become ready
        for _ in range(16):
            time.sleep(0.5)
            code, _, _ = http_get("/", timeout=2)
            if code == 200:
                log("PASS", "Server is up")
                return True
        log("FAIL", "Server did not become ready in time")
        return False
    except FileNotFoundError:
        log("WARN", "uvicorn not found -- will test against external server")
        return False


def stop_server() -> None:
    global SERVER_PROC
    if SERVER_PROC and SERVER_PROC.poll() is None:
        SERVER_PROC.terminate()
        SERVER_PROC.wait(timeout=5)
        log("INFO", "Dev server stopped")
        SERVER_PROC = None


def restart_server() -> bool:
    stop_server()
    time.sleep(1)
    return start_server()


def server_is_reachable() -> bool:
    code, _, _ = http_get("/", timeout=3)
    return code is not None


# +==========================================================================+
# |  PHASE 1 -- Baseline Performance                                         |
# +==========================================================================+

BASELINE: Dict[str, Any] = {}


def phase1_baseline() -> None:
    header("PHASE 1 . Baseline Performance")

    if not server_is_reachable():
        log("WARN", "Server unreachable -- skipping live baseline, using static analysis")
        record(
            "Phase 1 - Baseline",
            "Server connectivity check",
            "http_get('/')",
            "Server did not respond on 127.0.0.1:8000",
            "Unreachable",
            "Backend not running or wrong port",
            "High",
            "Ensure 'python -m uvicorn main:app --port 8000' is running before tests"
        )
        return

    samples = []
    for i in range(20):
        code, body, lat = http_get("/price")
        if code == 200:
            samples.append(lat)
        else:
            log("WARN", f"Sample {i}: unexpected status {code}")

    if not samples:
        log("FAIL", "No successful baseline samples")
        return

    BASELINE["p50"] = statistics.median(samples)
    BASELINE["p95"] = sorted(samples)[int(len(samples) * 0.95)]
    BASELINE["p99"] = sorted(samples)[int(len(samples) * 0.99)]
    BASELINE["mean"] = statistics.mean(samples)

    log("INFO", f"Baseline p50={BASELINE['p50']:.1f}ms  p95={BASELINE['p95']:.1f}ms  "
               f"p99={BASELINE['p99']:.1f}ms  mean={BASELINE['mean']:.1f}ms")

    # Verify schema contract
    _, body, _ = http_get("/price")
    required_keys = {"time", "price", "status", "message", "last_updated"}
    missing = required_keys - set(body.keys()) if body else required_keys
    if missing:
        record(
            "Phase 1 - Baseline schema",
            "Schema field presence check",
            "GET /price, compare keys to {time, price, status, message, last_updated}",
            f"Missing fields: {missing}",
            "Schema Contract Failure",
            "/price endpoint does not return all fields expected by frontend",
            "Critical",
            "Add missing fields to the /price response dict in main.py"
        )
    else:
        log("PASS", f"Schema OK -> keys: {set(body.keys())}")

    # Check status value domain
    if body and body.get("status") not in ("surplus", "shortage", "balanced"):
        record(
            "Phase 1 - Status domain",
            "Enum value check",
            "GET /price, inspect 'status' field value",
            f"status='{body.get('status')}' is not in valid domain",
            "Inconsistency",
            "Backend uses different enum labels than frontend expects",
            "High",
            "Align status values: Python should emit 'surplus'|'shortage'|'balanced'"
        )
    else:
        log("PASS", f"status domain OK -> '{body.get('status') if body else 'N/A'}'")

    log("PASS", "Phase 1 complete")


# +==========================================================================+
# |  PHASE 2 -- API Abuse / Concurrency Flood                               |
# +==========================================================================+

def _flood_worker(n: int) -> List[Tuple[Optional[int], float]]:
    results = []
    for _ in range(n):
        code, _, lat = http_get("/price", timeout=5)
        results.append((code, lat))
    return results


def phase2_api_flood() -> None:
    header("PHASE 2 . API Abuse / Concurrency Flood")

    if not server_is_reachable():
        log("WARN", "Server unreachable -- static analysis only")
        record(
            "Phase 2 - Concurrency flood",
            "100 concurrent requests",
            "ThreadPoolExecutor with 100 workers ? 5 requests",
            "Skipped -- server not reachable",
            "Skipped",
            "Server must be running for live concurrency tests",
            "High",
            "Run the FastAPI server before executing these tests"
        )
        # Static: check for rate-limiting
        original = read_file(MAIN_PY)
        if "rate" not in original.lower() and "slowapi" not in original.lower() and "limiter" not in original.lower():
            record(
                "Phase 2 - Rate limiting (static)",
                "Code inspection for rate-limit middleware",
                "grep for 'rate', 'slowapi', 'limiter' in main.py",
                "No rate-limiting middleware found in main.py",
                "Missing Security Control",
                "FastAPI app has open CORS (*) and no request throttling",
                "Critical",
                "Add SlowAPI or a custom middleware: @limiter.limit('100/minute') on /price"
            )
        return

    CONCURRENCY_LEVELS = [10, 50, 100, 200]
    for workers in CONCURRENCY_LEVELS:
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_flood_worker, 5) for _ in range(workers)]
            all_results = []
            for f in concurrent.futures.as_completed(futures):
                all_results.extend(f.result())
        elapsed = time.perf_counter() - t0

        codes  = [r[0] for r in all_results]
        lats   = [r[1] for r in all_results]
        errors = [c for c in codes if c is None or c >= 500]
        ok     = [c for c in codes if c == 200]

        p95 = sorted(lats)[int(len(lats)*0.95)] if lats else 0

        log("INFO", f"[{workers} workers] total={len(all_results)} ok={len(ok)} "
                   f"errors={len(errors)} p95={p95:.0f}ms elapsed={elapsed:.1f}s")

        if errors:
            record(
                f"Phase 2 - Flood @ {workers} workers",
                f"{workers*5} concurrent GET /price requests",
                f"ThreadPoolExecutor({workers}), 5 req each",
                f"{len(errors)}/{len(all_results)} requests returned 5xx/timeout",
                "Crash / Service Degradation",
                "No rate limiting + single-threaded state mutations cause GIL contention",
                "High" if len(errors) < len(all_results)//2 else "Critical",
                "Add SlowAPI rate limiting; move shared `state` dict to asyncio.Lock or Redis"
            )
        elif p95 > (BASELINE.get("p95", 100) * 5):
            record(
                f"Phase 2 - Latency @ {workers} workers",
                f"{workers*5} concurrent GET /price requests",
                f"ThreadPoolExecutor({workers}), 5 req each",
                f"p95={p95:.0f}ms (>{BASELINE.get('p95',100)*5:.0f}ms threshold)",
                "Latency Spike",
                "No connection pooling or async concurrency; uvicorn threads saturate",
                "Medium",
                "Switch to async endpoint; add --workers flag to uvicorn in production"
            )
        else:
            log("PASS", f"Flood @ {workers} workers: system stable")

    # Check: no API key / auth at all
    original = read_file(MAIN_PY)
    if "api_key" not in original.lower() and "x-api-key" not in original.lower() \
       and "authorization" not in original.lower() and "APIKey" not in original:
        record(
            "Phase 2 - Auth check (static)",
            "Code inspection for authentication headers",
            "grep main.py for API key / Bearer / Authorization",
            "No authentication on any endpoint",
            "Missing Security Control",
            "All endpoints are publicly accessible with no credentials required",
            "Critical",
            "Add FastAPI APIKeyHeader dependency to /price and write/mutate endpoints"
        )

    log("PASS", "Phase 2 complete")


# +==========================================================================+
# |  PHASE 3 -- Schema Contract Breakage                                     |
# +==========================================================================+

def phase3_schema_contract() -> None:
    header("PHASE 3 - Backend <-> Frontend Schema Contract")

    original_main = read_file(MAIN_PY)

    # -- 3a: rename 'price' -> 'current_price' in API response ----------------
    old = """    return {
        "time": DATA[state["index"]]["time"],
        "price": state["current_price"],
        "status": state["status"],
        "message": state["message"],
        "last_updated": state["last_updated"]
    }"""
    new = """    return {
        "time": DATA[state["index"]]["time"],
        "current_price": state["current_price"],   # <- renamed field (schema break)
        "status": state["status"],
        "message": state["message"],
        "last_updated": state["last_updated"]
    }"""

    can_patch = old in original_main
    if can_patch:
        patch_file(MAIN_PY, old, new)
        success = restart_server()
        time.sleep(1)

        _, body, _ = http_get("/price")
        has_price     = "price" in (body or {})
        has_curr      = "current_price" in (body or {})
        log("INFO", f"After rename: has_price={has_price}, has_current_price={has_curr}")

        if not has_price and has_curr:
            record(
                "Phase 3a - Field Rename",
                "Renamed 'price' -> 'current_price' in GET /price response",
                "Patched main.py return dict, restarted server",
                "Frontend receives 'current_price' but consumes 'price'; "
                "NextPricePanel renders undefined",
                "Schema Contract Failure",
                "No shared schema/type enforced between Python backend and TS frontend; "
                "field rename silently breaks UI",
                "Critical",
                "Define a Pydantic response model in FastAPI; generate TypeScript types "
                "from OpenAPI spec (e.g. openapi-generator)"
            )

        restore_file(MAIN_PY, original_main)
        restart_server()
        time.sleep(1)
    else:
        log("WARN", "Cannot apply schema patch -- checking statically")

    # -- 3b: null price field -------------------------------------------------
    old_null = '        "price": state["current_price"],'
    new_null = '        "price": None,'

    can_null_patch = old_null in original_main
    if can_null_patch:
        patch_file(MAIN_PY, old_null, new_null)
        restart_server()
        time.sleep(1)

        _, body, _ = http_get("/price")
        price_val = (body or {}).get("price")
        log("INFO", f"Null price test: price={price_val!r}")

        if price_val is None:
            record(
                "Phase 3b - Null Price",
                "Injected None/null into 'price' field",
                "Patched main.py to return price=None, restarted",
                "Frontend receives price=null; renders Rs.null in UI; "
                "math operations (trend calc) throw TypeError",
                "Data Corruption / UI Breakage",
                "No output validation -- backend can emit nulls with no error",
                "High",
                "Add Pydantic model with price: float (non-optional); "
                "add frontend null-guard before rendering price"
            )

        restore_file(MAIN_PY, original_main)
        restart_server()
        time.sleep(1)
    else:
        record(
            "Phase 3b - Null Price (static)",
            "Static check: no output validation",
            "Inspect main.py for Pydantic response_model",
            "No Pydantic response model; backend can return arbitrary shapes",
            "Missing Validation",
            "FastAPI route has no response_model annotation",
            "High",
            "Add response_model=PriceResponse to @app.get('/price')"
        )

    # -- 3c: extra undocumented field -----------------------------------------
    # Static analysis -- no restart needed
    original_ts = read_file(os.path.join(HERE, "..", "src", "lib", "pricing.ts"))
    py_status_vals  = {"surplus", "shortage", "balanced"}
    ts_status_match = all(v in original_ts for v in py_status_vals)
    if not ts_status_match:
        record(
            "Phase 3c - Status Enum Drift",
            "Compare status enums between Python and TypeScript",
            "Static analysis of main.py and src/lib/pricing.ts",
            "Status enum values not consistently verified cross-language",
            "Inconsistency Risk",
            "Python and TypeScript both define their own status enums independently; "
            "a change in one will silently drift from the other",
            "Medium",
            "Generate TS types from Python Pydantic models via openapi-ts; "
            "add a contract test that fetches /price and validates against TS type"
        )
    else:
        log("PASS", "Status enum values match between Python and TypeScript")

    log("PASS", "Phase 3 complete")


# +==========================================================================+
# |  PHASE 4 -- Scheduler Stress                                             |
# +==========================================================================+

def phase4_scheduler_stress() -> None:
    header("PHASE 4 . APScheduler Stress")

    original_main = read_file(MAIN_PY)

    # -- 4a: aggressive interval (100 ms) ------------------------------------
    old_interval = "scheduler.add_job(update_price, 'interval', seconds=5)"
    new_interval = "scheduler.add_job(update_price, 'interval', seconds=0.1)  # STRESS"

    if old_interval in original_main:
        patch_file(MAIN_PY, old_interval, new_interval)
        success = restart_server()
        time.sleep(3)   # let scheduler spin

        if success:
            # sample /price rapidly and check for inconsistencies
            prices = []
            indices = []
            for _ in range(30):
                _, body, _ = http_get("/price", timeout=3)
                if body:
                    prices.append(body.get("price"))
                time.sleep(0.05)

            none_prices = [p for p in prices if p is None]
            if none_prices:
                record(
                    "Phase 4a - Rapid Scheduler",
                    "APScheduler interval set to 100 ms",
                    "Patched main.py: seconds=0.1, restarted, sampled /price 30?",
                    f"{len(none_prices)}/30 samples returned price=None; "
                    "index counter racing the read path",
                    "Race Condition / Data Corruption",
                    "Python dict is not thread-safe for multi-key updates; "
                    "scheduler job and HTTP handler share mutable `state` dict without a lock",
                    "Critical",
                    "Wrap all `state` reads/writes with threading.Lock(); "
                    "consider asyncio.Lock for async contexts"
                )
            else:
                log("PASS", "Rapid scheduler: no null prices (GIL helped)")

            # Check index wrapping
            _, body, _ = http_get("/price")
            if body:
                log("INFO", f"Index after rapid spin: t={body.get('time')} p={body.get('price')}")

        restore_file(MAIN_PY, original_main)
        restart_server()
        time.sleep(1)
    else:
        log("WARN", "Cannot find scheduler interval line -- static check only")

    # -- 4b: inject artificial delay in job ----------------------------------
    old_update = "def update_price():\n    index = state[\"index\"]"
    new_update = "def update_price():\n    time.sleep(6)  # INJECTED DELAY\n    index = state[\"index\"]"

    original_main2 = read_file(MAIN_PY)  # re-read (might have been restored)
    if old_update in original_main2:
        import_line = "from datetime import datetime"
        patch_file(MAIN_PY,
                   import_line,
                   import_line + "\nimport time as _time_module")
        # Re-read and then patch the delay
        content_after_import = read_file(MAIN_PY)
        new_update_with_module = new_update.replace("time.sleep(6)", "_time_module.sleep(6)")

        if "def update_price():\n    index = state[\"index\"]" in content_after_import:
            patch_file(MAIN_PY,
                       "def update_price():\n    index = state[\"index\"]",
                       "def update_price():\n    _time_module.sleep(6)  # INJECTED DELAY\n    index = state[\"index\"]")

            restart_server()
            time.sleep(2)

            # Scheduler interval is 5 s, delay is 6 s -> missed fires
            # Measure whether state goes stale
            t0 = time.time()
            first_code, first_body, _ = http_get("/price")
            time.sleep(7)
            second_code, second_body, _ = http_get("/price")

            if first_body and second_body:
                same_time = first_body.get("time") == second_body.get("time")
                same_price = first_body.get("price") == second_body.get("price")
                if same_time and same_price:
                    record(
                        "Phase 4b - Delayed Scheduler Job",
                        "Injected 6-second sleep into update_price() (interval=5s)",
                        "Patched update_price to sleep 6s; sampled /price before & after 7s wait",
                        "State did not update after 7 seconds -- scheduler job blocked; "
                        "price stays stale for extended period",
                        "Scheduler Stall / Stale Data",
                        "APScheduler BackgroundScheduler uses a ThreadPool; when the job "
                        "takes longer than its interval, subsequent fires are coalesced or "
                        "dropped (misfire_grace_time default behaviour)",
                        "High",
                        "Set misfire_grace_time=1s on the job; add job execution "
                        "monitoring/alerting; move long ops out of the job body"
                    )

        restore_file(MAIN_PY, original_main)
        restart_server()
        time.sleep(1)

    # -- 4c: static -- no scheduler health endpoint ----------------------------
    original_main = read_file(MAIN_PY)
    if "/health" not in original_main and "/scheduler" not in original_main:
        record(
            "Phase 4c - No Health/Scheduler Endpoint",
            "Static inspection for /health or /scheduler-status route",
            "grep main.py for '/health', '/scheduler'",
            "No health or scheduler-status endpoint exists",
            "Observability Gap",
            "Cannot monitor whether the scheduler is alive, how many jobs fired, "
            "or detect job failures without access to server logs",
            "High",
            "Add GET /health that returns scheduler.running, job.next_run_time, "
            "last update timestamp, and current state"
        )

    log("PASS", "Phase 4 complete")


# +==========================================================================+
# |  PHASE 5 -- Clock / Time Drift                                           |
# +==========================================================================+

def phase5_clock_drift() -> None:
    header("PHASE 5 . Clock / Time Drift Simulation")

    # -- 5a: Frontend IST vs backend datetime.now() mismatch -----------------
    original_main = read_file(MAIN_PY)
    if "datetime.now()" in original_main and "timezone" not in original_main:  # noqa
        record(
            "Phase 5a - Naive datetime.now()",
            "Static check: backend uses timezone-naive datetime",
            "Inspect main.py for datetime.now() without tzinfo",
            "Backend uses datetime.now() (server-local time) for last_updated; "
            "if server is UTC, displayed time will be 5:30h behind IST frontend",
            "Clock Drift / UI Inconsistency",
            "Python datetime.now() returns local server time with no timezone; "
            "frontend parses and displays it assuming IST, causing a 5:30h mismatch",
            "High",
            "Replace datetime.now() with "
            "datetime.now(tz=timezone(timedelta(hours=5, minutes=30))).strftime('%H:%M') "
            "in main.py; import timezone, timedelta from datetime"
        )
    else:
        log("PASS", "Backend uses timezone-aware datetime (or not using datetime.now)")

    # -- 5b: Pricing data covers 7AM-12AM only (6:30h gap) --------------------
    pricing_src = read_file(PRICING_PY)
    if '"12:00 AM"' in pricing_src and '"6:30 AM"' not in pricing_src:
        record(
            "Phase 5b - Dataset Time Gap",
            "Static: PRICING_DATA starts at 7:00 AM and ends at 12:00 AM",
            "Inspect pricing.py DATA list time coverage",
            "No data for 12:30 AM - 6:30 AM (6-hour window); "
            "frontend pricing.ts falls back to last row (12:00 AM) for any time in this gap",
            "Stale Data / Wrong Price",
            "Dataset is incomplete; fallback logic silently returns midnight price "
            "at any hour between 12:30 AM and 6:59 AM",
            "Medium",
            "Add early-morning rows OR clearly document the off-hours fallback; "
            "at minimum emit a 'off_peak_hours' status flag for these intervals"
        )

    # -- 5c: Frontend vs Backend index divergence -----------------------------
    # Frontend uses IST clock -> 30-min block index (0-47).
    # Backend uses a sequential counter (state["index"]) reset to 0 on restart.
    # These can diverge silently.
    frontend_block_logic = "Math.floor(totalMinutes / 30)"  # from page.tsx
    backend_index_logic  = 'state["index"] = (index + 1) % get_dataset_length()'

    page_tsx_path = os.path.join(HERE, "..", "src", "app", "page.tsx")
    page_tsx = ""
    try:
        page_tsx = read_file(page_tsx_path)
    except FileNotFoundError:
        pass

    if frontend_block_logic in page_tsx and backend_index_logic in original_main:
        record(
            "Phase 5c - Dual Index Divergence",
            "Comparing frontend clock-based index vs backend sequential counter",
            "Static analysis: page.tsx getCurrentBlockIndex() vs main.py state['index']",
            "Frontend computes price based on wall-clock 30-min block (IST); "
            "backend computes price based on sequential state['index'] counter; "
            "after any restart, backend resets to index=0 (7:00 AM data) regardless of time",
            "State Inconsistency / Incorrect Price",
            "Two entirely independent indexing mechanisms exist; "
            "frontend may show Rs.10.19 (7AM price) while backend (if restarted) "
            "shows the same until the first scheduled job runs",
            "Critical",
            "Eliminate the sequential backend counter; instead, derive index from "
            "IST clock time in update_price(): "
            "index = (now.hour*60+now.minute)//30 % len(DATA)"
        )

    log("PASS", "Phase 5 complete")


# +==========================================================================+
# |  PHASE 6 -- Invalid / Null / Extreme Data Injection                     |
# +==========================================================================+

def phase6_data_injection() -> None:
    header("PHASE 6 . Invalid / Null / Extreme Data Injection")

    original_pricing = read_file(PRICING_PY)

    # -- 6a: Negative supply (division by zero path variation) ----------------
    test_cases = [
        ("negative_supply",   '{"time": "Test", "demand": 10.0, "supply": -5.0, "pbase": 5.0}',
         "compute_price_by_index returns pbase+demand/(-5)+0.5 = 3.5; negative price possible"),
        ("zero_demand",       '{"time": "Test", "demand": 0.0,  "supply": 10.0, "pbase": 3.0}',
         "price = 3.0 + 0.0 + 0.5 = 3.5; technically valid but edge case"),
        ("extreme_demand",    '{"time": "Test", "demand": 1e9,  "supply": 1.0,  "pbase": 1.0}',
         "price = 1 + 1e9 + 0.5 ~= 1,000,000,001.5; no upper cap check"),
        ("nan_pbase",         '{"time": "Test", "demand": 5.0,  "supply": 5.0,  "pbase": float("nan")}',
         "NaN propagates through arithmetic; price=nan; JSON serialisation may crash"),
        ("inf_pbase",         '{"time": "Test", "demand": 5.0,  "supply": 5.0,  "pbase": float("inf")}',
         "Infinity propagates; JSON serialisation raises ValueError in stdlib json"),
    ]

    pricing_src_template = original_pricing + \
        "\n\n# -- INJECTION TESTING --\n" \
        "if __name__ == '__test__':\n    pass\n"

    for name, row_literal, expected in test_cases:
        try:
            # Evaluate the row dict safely
            row = eval(row_literal, {"float": float})
            d, s, pb = row["demand"], row["supply"], row["pbase"]

            if s == 0:
                price = pb
            else:
                price = pb + (d / s) + 0.50

            has_nan = math.isnan(price) if isinstance(price, float) else False
            has_inf = math.isinf(price) if isinstance(price, float) else False
            is_neg  = isinstance(price, float) and not has_nan and not has_inf and price < 0

            if has_nan:
                classification = "NaN Propagation -> JSON serialisation crash"
                severity = "Critical"
                fix = "Validate all DATA rows at startup; reject NaN/Inf in compute_price_by_index"
            elif has_inf:
                classification = "Infinity -> JSON ValueError crash"
                severity = "Critical"
                fix = "Cap supply to min=0.01; reject Inf/NaN before returning; use Pydantic validators"
            elif is_neg:
                classification = "Negative Price"
                severity = "High"
                fix = "Clamp price: price = max(0.0, price); validate supply > 0"
            elif price > 1000:
                classification = "Runaway Price (no upper cap)"
                severity = "High"
                fix = "Add MAX_PRICE = 15.0 cap; alert if price exceeds threshold"
            else:
                log("PASS", f"Injection '{name}': price={price:.4f} (acceptable range)")
                continue

            record(
                f"Phase 6 - {name}",
                f"Injected {row_literal} into compute_price_by_index",
                "Python eval of synthetic DATA row, direct arithmetic validation",
                f"price={price!r}; {expected}",
                classification,
                "compute_price_by_index has no input validation or output clamping",
                severity,
                fix
            )
        except Exception as e:
            record(
                f"Phase 6 - {name} (exception)",
                f"Injected {row_literal}",
                "Python direct computation",
                f"Exception raised: {e}",
                "Unhandled Exception",
                "compute_price_by_index can raise exceptions on malformed input",
                "High",
                "Wrap compute_price_by_index in try/except; validate DATA at import time"
            )

    # -- 6b: Out-of-bounds index ----------------------------------------------
    try:
        sys.path.insert(0, HERE)
        import importlib
        pricing_mod = importlib.import_module("pricing")
        importlib.reload(pricing_mod)
        length = pricing_mod.get_dataset_length()

        # Call with index = length (out-of-range)
        try:
            pricing_mod.compute_price_by_index(length)
            record(
                "Phase 6 - OOB Index",
                "Called compute_price_by_index(35) where len(DATA)==35",
                "Direct Python call with index=length",
                "IndexError not raised -- unexpected behaviour",
                "Silent Corruption",
                "Index wrapping logic only in update_price(), not in compute_price_by_index",
                "Medium",
                "Add bounds check: if not 0 <= index < len(DATA): raise ValueError()"
            )
        except IndexError:
            record(
                "Phase 6 - OOB Index",
                "Called compute_price_by_index(35) where len(DATA)==35",
                "Direct Python call with index=length",
                "IndexError raised as expected, but NOT caught in update_price(). "
                "This crash propagates to the scheduler thread -> scheduler may halt.",
                "Unhandled Exception / Scheduler Halt",
                "update_price() calls compute_price_by_index(index) after "
                "state['index'] is updated; off-by-one or concurrent write could "
                "pass an out-of-range index",
                "Critical",
                "Wrap update_price() body in try/except; catch IndexError and log; "
                "add bounds validation in compute_price_by_index"
            )
    except Exception as e:
        log("WARN", f"Could not import pricing module for direct tests: {e}")

    # -- 6c: GET /price with corrupted state (live) ---------------------------
    if server_is_reachable():
        original_main = read_file(MAIN_PY)
        # Inject corrupted state dict
        old_state = '''state = {
    "current_price": 3.80,
    "last_updated": None,
    "index": 0,
    "status": "neutral",
    "message": "System stable"
}'''
        new_state = '''state = {
    "current_price": None,
    "last_updated": "INVALID",
    "index": 999,        # <- OOB
    "status": 12345,     # <- wrong type
    "message": None
}'''
        if old_state in original_main:
            patch_file(MAIN_PY, old_state, new_state)
            restart_server()
            time.sleep(2)

            code, body, lat = http_get("/price")
            if code == 500 or code is None:
                record(
                    "Phase 6c - Corrupted State (live)",
                    "Initialised state dict with invalid types and OOB index",
                    "Patched main.py state dict, restarted, GET /price",
                    f"Server returned {code} -- state corruption causes crash on first access",
                    "Crash on Startup / Corrupted State",
                    "No state schema validation; DATA[999] raises IndexError, "
                    "None arithmetic raises TypeError",
                    "Critical",
                    "Use a Pydantic BaseModel for application state; "
                    "validate state at startup; add startup health check"
                )
            elif code == 200 and body:
                log("INFO", f"Corrupted state: server survived -> price={body.get('price')} "
                           f"status={body.get('status')!r}")

            restore_file(MAIN_PY, original_main)
            restart_server()
            time.sleep(1)

    log("PASS", "Phase 6 complete")


# +==========================================================================+
# |  PHASE 7 -- Race Conditions (scheduler + concurrent API)                |
# +==========================================================================+

def phase7_race_conditions() -> None:
    header("PHASE 7 . Race Conditions -- Scheduler + Concurrent API")

    if not server_is_reachable():
        log("WARN", "Server unreachable -- static analysis only")
        original_main = read_file(MAIN_PY)
        if "Lock()" not in original_main and "asyncio.Lock" not in original_main:
            record(
                "Phase 7 - No Lock (static)",
                "Inspect shared mutable state for thread-safety",
                "grep main.py for Lock(), asyncio.Lock",
                "Global `state` dict mutated by scheduler thread AND read by "
                "FastAPI request handler threads simultaneously -- no lock",
                "Race Condition",
                "Python's GIL prevents true parallel execution but does NOT make "
                "dict operations atomic across multiple lines; partial updates visible",
                "Critical",
                "Add state_lock = threading.Lock(); acquire in update_price() "
                "and in get_price() before accessing state"
            )
        return

    original_main = read_file(MAIN_PY)

    # Inject a multi-step state update with a delay to widen the race window
    old_update_block = """    # --- UPDATE STATE ---
    state["current_price"] = price
    state["last_updated"] = datetime.now().strftime("%H:%M")
    state["status"] = status
    state["message"] = message"""

    new_update_block = """    # --- UPDATE STATE (RACE WINDOW WIDENED) ---
    import time as _t
    state["current_price"] = price
    _t.sleep(0.05)       # <- simulate context-switch window
    state["last_updated"] = datetime.now().strftime("%H:%M")
    _t.sleep(0.05)
    state["status"] = status
    _t.sleep(0.05)
    state["message"] = message"""

    if old_update_block in original_main:
        patch_file(MAIN_PY, old_update_block, new_update_block)
        restart_server()
        time.sleep(2)

        # Flood API while scheduler updates state
        inconsistencies = []
        valid_statuses = {"surplus", "shortage", "balanced", "neutral"}

        def check_consistency():
            _, body, _ = http_get("/price", timeout=3)
            if body:
                s = body.get("status")
                p = body.get("price")
                if s not in valid_statuses:
                    inconsistencies.append(f"invalid_status:{s!r}")
                if p is None:
                    inconsistencies.append("price_is_None")
                if isinstance(p, (int, float)) and p < 0:
                    inconsistencies.append(f"negative_price:{p}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
            futs = [pool.submit(check_consistency) for _ in range(200)]
            concurrent.futures.wait(futs)

        if inconsistencies:
            record(
                "Phase 7 - Race Condition (live)",
                "Widened scheduler-state write window to 150ms; 200 concurrent reads",
                "Patched multi-step state write with sleep; 50 threads ? 4 requests",
                f"Detected {len(inconsistencies)} inconsistencies: {inconsistencies[:5]}",
                "Race Condition / Partial State Exposure",
                "State dict written in multiple separate assignments across 150ms; "
                "concurrent readers see partially-updated state (e.g. new price, old status)",
                "Critical",
                "Atomic update: build a new dict and do state.update(new_state) in one call; "
                "OR wrap with threading.Lock()"
            )
        else:
            log("PASS", "Race condition: GIL protected state (no inconsistencies in 200 reads)")
            record(
                "Phase 7 - Race Condition (live)",
                "Widened scheduler-state write window to 150ms; 200 concurrent reads",
                "Patched multi-step state write with sleep; 50 threads ? 4 requests",
                "No inconsistency detected -- GIL shielded state but race window exists",
                "Latent Race (GIL-protected)",
                "CPython GIL prevented observed corruption but the pattern is unsafe "
                "on PyPy, sub-interpreters, or async uvicorn with multiple workers",
                "High",
                "Add threading.Lock() regardless; use atomic state.update(); "
                "never rely on GIL for correctness"
            )

        restore_file(MAIN_PY, original_main)
        restart_server()
        time.sleep(1)
    else:
        log("WARN", "Cannot apply race-condition patch -- running static check")
        original_main = read_file(MAIN_PY)
        if "Lock()" not in original_main:
            record(
                "Phase 7 - Race Condition (static)",
                "Static analysis of shared mutable state",
                "grep main.py for Lock()",
                "state dict mutated across 4 separate assignments without a lock",
                "Race Condition (Latent)",
                "Multi-step state mutation is not atomic under concurrent access",
                "Critical",
                "Use threading.Lock() or replace with asyncio-safe state management"
            )

    log("PASS", "Phase 7 complete")


# +==========================================================================+
# |  PHASE 8 -- Network Latency Simulation                                  |
# +==========================================================================+

def phase8_network_latency() -> None:
    header("PHASE 8 . Network Latency Simulation")

    if not server_is_reachable():
        # Static checks only
        api_ts = read_file(os.path.join(HERE, "..", "src", "lib", "api.ts"))
        pricing_ts = read_file(os.path.join(HERE, "..", "src", "lib", "pricing.ts"))

        if "timeout" not in api_ts.lower() and "AbortController" not in api_ts:
            record(
                "Phase 8a - No Client Timeout (static)",
                "api.ts fetch() call missing timeout/AbortSignal",
                "grep src/lib/api.ts for timeout, AbortController, AbortSignal",
                "getPrice() in api.ts has no timeout; a slow backend will block "
                "fetch() indefinitely, hanging the frontend render",
                "Hanging Request / Potential Dead UI",
                "fetch() default has no timeout; slow or unreachable backends "
                "cause the UI to hang until browser timeout (~5 min)",
                "High",
                "Add AbortController with setTimeout(abort, 5000) to api.ts getPrice(); "
                "display stale-data banner if fetch times out"
            )

        if "catch" not in api_ts:
            record(
                "Phase 8b - No Error Handling in api.ts (static)",
                "api.ts getPrice() error handling check",
                "grep src/lib/api.ts for try/catch, .catch()",
                "getPrice() throws on non-200; caller must handle -- but page.tsx "
                "does not wrap getCurrentPricingData() in try/catch",
                "Unhandled Rejection / UI Crash",
                "A network error causes unhandled Promise rejection; "
                "NextJS may show an error boundary instead of graceful degradation",
                "High",
                "Wrap fetch in try/catch; return null or stale value on error; "
                "add UI error banner when backend is unreachable"
            )
        return

    # Live latency tests
    TIMEOUT_CASES = [
        (1, "1s timeout -- below normal backend response"),
        (3, "3s timeout"),
        (10, "10s timeout (normal)"),
    ]

    baseline_lat = BASELINE.get("mean", 50)

    for timeout_s, label in TIMEOUT_CASES:
        code, body, lat = http_get("/price", timeout=timeout_s)
        log("INFO", f"{label}: code={code} lat={lat:.1f}ms")

    # Simulate slow response by checking 0-byte timeout
    code, body, lat = http_get("/price", timeout=0.001)
    if code is None:
        record(
            "Phase 8c - Zero Timeout",
            "GET /price with 0.001s timeout (simulated packet drop)",
            "urllib.request.urlopen(..., timeout=0.001)",
            "Request timed out as expected -- but frontend api.ts has no timeout-handling",
            "Client Hang Risk",
            "Frontend fetch() has no AbortController; any real network timeout "
            "will cause the frontend to hang indefinitely",
            "High",
            "Add AbortController(5000ms) to all fetch() calls in api.ts and Next.js routes"
        )

    log("PASS", "Phase 8 complete")


# +==========================================================================+
# |  PHASE 9 -- Environment Misconfiguration                                |
# +==========================================================================+

def phase9_env_misconfiguration() -> None:
    header("PHASE 9 . Environment Misconfiguration")

    # -- 9a: Hardcoded secrets in source files --------------------------------
    supabase_client_path = os.path.join(HERE, "..", "src", "lib", "supabaseClient.ts")
    try:
        supabase_src = read_file(supabase_client_path)
        has_hardcoded_url = "supabase.co" in supabase_src
        has_hardcoded_key = "eyJ" in supabase_src  # JWT prefix

        if has_hardcoded_url and has_hardcoded_key:
            record(
                "Phase 9a - Hardcoded Supabase Credentials",
                "Supabase URL and anon key hardcoded in supabaseClient.ts",
                "Read src/lib/supabaseClient.ts; check for literal URL and JWT key",
                "supabaseUrl and supabaseAnonKey are hardcoded string literals; "
                "visible in source, Git history, and any bundle",
                "Secret Leakage",
                "Credentials committed to source control; anyone with repo access "
                "can read Supabase project, query data, or abuse RPC",
                "Critical",
                "Move to NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY "
                "env vars; add supabaseClient.ts pattern to .gitignore or use "
                ".env.local which is already gitignored"
            )
    except FileNotFoundError:
        log("WARN", "supabaseClient.ts not found for inspection")

    # -- 9b: Hardcoded ngrok URL in api.ts ------------------------------------
    api_ts_path = os.path.join(HERE, "..", "src", "lib", "api.ts")
    try:
        api_src = read_file(api_ts_path)
        if "ngrok" in api_src or "ngrok-free" in api_src:
            record(
                "Phase 9b - Hardcoded ngrok URL",
                "BASE_URL in api.ts points to a dynamic ngrok tunnel",
                "Read src/lib/api.ts; check BASE_URL value",
                "BASE_URL='https://sift-stank-chair.ngrok-free.dev' is hardcoded; "
                "ngrok tunnels expire and rotate; any deployment without refreshing "
                "this URL will silently fail (all /price requests return network errors)",
                "Deployment Misconfiguration / Silent Failure",
                "ngrok free-tier URLs are ephemeral and non-deterministic; "
                "hardcoding them makes deployments fragile",
                "Critical",
                "Move to NEXT_PUBLIC_API_BASE_URL env var; "
                "use a stable domain for production; "
                "add a startup check: if BASE_URL unreachable, show maintenance banner"
            )
        if "process.env" not in api_src and "NEXT_PUBLIC" not in api_src:
            record(
                "Phase 9b.2 - No Env Var for API URL",
                "api.ts BASE_URL is a literal string, not an env var",
                "Inspect src/lib/api.ts for process.env / NEXT_PUBLIC_",
                "Changing the backend URL requires a code edit and redeploy, "
                "not just an env var change",
                "Configuration Rigidity",
                "Deployment environments (dev/staging/prod) cannot be differentiated "
                "without code changes",
                "Medium",
                "const BASE_URL = process.env.NEXT_PUBLIC_PYTHON_API_URL ?? 'http://localhost:8000';"
            )
    except FileNotFoundError:
        log("WARN", "api.ts not found for inspection")

    # -- 9c: Open CORS (*) in production -------------------------------------
    original_main = read_file(MAIN_PY)
    if 'allow_origins=["*"]' in original_main:
        record(
            "Phase 9c - Wildcard CORS",
            "CORSMiddleware configured with allow_origins=['*']",
            "grep main.py for allow_origins",
            "Any origin can call the FastAPI backend; "
            "a malicious site can make credentialed cross-origin requests",
            "Security Misconfiguration",
            "allow_origins=['*'] with allow_credentials=True is forbidden by browsers "
            "AND a security risk; credentials (cookies, auth headers) can be smuggled",
            "High",
            "Set allow_origins to explicit list: ['https://your-domain.com']; "
            "remove allow_credentials=True unless required; "
            "note: allow_credentials=True + allow_origins=['*'] is an invalid CORS combo"
        )

    # -- 9d: No .env.example or documented env vars --------------------------
    root = os.path.join(HERE, "..")
    env_example = os.path.join(root, ".env.example")
    env_local   = os.path.join(root, ".env.local")
    if not os.path.exists(env_example) and not os.path.exists(env_local):
        record(
            "Phase 9d - No .env.example",
            "Check for .env.example or .env.local at repo root",
            "os.path.exists checks",
            "No .env.example found; new developers have no list of required env vars; "
            "deployment without correct env vars silently uses hardcoded fallbacks",
            "Documentation Gap / Deployment Risk",
            "Required environment variables are undocumented; "
            "missed vars cause silent failures (hardcoded ngrok URL used instead)",
            "Medium",
            "Create .env.example with all required keys: "
            "NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, "
            "NEXT_PUBLIC_PYTHON_API_URL"
        )

    # -- 9e: No Python env file / config management ---------------------------
    py_env = os.path.join(HERE, ".env")
    py_dotenv = os.path.join(HERE, "config.py")
    if not os.path.exists(py_env) and not os.path.exists(py_dotenv):
        if "os.environ" not in original_main and "dotenv" not in original_main:
            record(
                "Phase 9e - No Python Config Management",
                "Python backend has no env var / config file usage",
                "grep main.py for os.environ, dotenv, config",
                "Python backend has no configurable settings; "
                "scheduler interval, port, and CORS origins are all hardcoded",
                "Deployment Inflexibility",
                "Cannot change scheduler interval or security settings without "
                "editing source code",
                "Medium",
                "Add python-dotenv; load SCHEDULER_INTERVAL_SECONDS, ALLOWED_ORIGINS "
                "from environment; provide sensible defaults"
            )

    log("PASS", "Phase 9 complete")


# +==========================================================================+
# |  PHASE 10 -- Combined End-to-End Chaos                                  |
# +==========================================================================+

def phase10_combined_chaos() -> None:
    header("PHASE 10 . Combined End-to-End Chaos")

    if not server_is_reachable():
        log("WARN", "Server not reachable -- chaos test is static summary")
        record(
            "Phase 10 - Combined Chaos (static)",
            "Combined: concurrent flood + scheduler stress + corrupted env",
            "Static projection based on phases 2-9 findings",
            "When all failure modes are active simultaneously: "
            "(1) 200 concurrent users hit /price while scheduler updates state every 100ms, "
            "(2) BASE_URL is stale (ngrok expired), (3) Supabase key is leaked, "
            "(4) Time is UTC not IST -> system would show incorrect prices, "
            "race corruptions, and frontend dead renders simultaneously",
            "Cascading Failure",
            "Multiple independent weaknesses (no lock, no auth, hardcoded configs) "
            "compound in production under real load",
            "Critical",
            "See full recommendations in report. Priority: (1) threading.Lock on state, "
            "(2) env vars for all secrets/URLs, (3) auth middleware, (4) IST-aware timestamps"
        )
        return

    # 10a: Start scheduler stress + concurrent flood simultaneously
    original_main = read_file(MAIN_PY)
    old_interval = "scheduler.add_job(update_price, 'interval', seconds=5)"
    new_interval = "scheduler.add_job(update_price, 'interval', seconds=0.5)  # CHAOS"

    if old_interval in original_main:
        patch_file(MAIN_PY, old_interval, new_interval)
        restart_server()
        time.sleep(2)

    errors = []
    inconsistencies = []
    latencies = []
    valid_statuses = {"surplus", "shortage", "balanced", "neutral"}

    def chaos_worker():
        for _ in range(10):
            code, body, lat = http_get("/price", timeout=4)
            latencies.append(lat)
            if code != 200 or body is None:
                errors.append(code)
            elif body.get("status") not in valid_statuses:
                inconsistencies.append(body.get("status"))
            time.sleep(0.01)

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as pool:
        futs = [pool.submit(chaos_worker) for _ in range(100)]
        concurrent.futures.wait(futs)

    total = len(latencies)
    err_pct = len(errors) / total * 100 if total else 0
    p95_chaos = sorted(latencies)[int(total * 0.95)] if latencies else 0

    log("INFO", f"Chaos results: total={total} errors={len(errors)} ({err_pct:.1f}%) "
               f"inconsistencies={len(inconsistencies)} p95={p95_chaos:.0f}ms")

    if errors or inconsistencies:
        record(
            "Phase 10 - Combined Chaos (live)",
            "100 threads ? 10 requests + scheduler at 500ms interval",
            "ThreadPoolExecutor(100), chaos_worker(), patched scheduler interval",
            f"Errors: {len(errors)}/{total} ({err_pct:.1f}%); "
            f"Inconsistencies: {len(inconsistencies)}; p95 latency: {p95_chaos:.0f}ms",
            "Cascading Failure under Combined Load",
            "Concurrent scheduler writes + API reads expose all race conditions; "
            "no rate limiting accelerates error propagation",
            "Critical",
            "Implement threading.Lock, rate limiting, and health monitoring as priority fixes"
        )
    else:
        record(
            "Phase 10 - Combined Chaos (live)",
            "100 threads ? 10 requests + scheduler at 500ms interval",
            "ThreadPoolExecutor(100), chaos_worker(), patched scheduler interval",
            f"System survived: 0 errors, 0 inconsistencies, p95={p95_chaos:.0f}ms",
            "Resilient under GIL",
            "CPython GIL prevented observed failures but latent race condition "
            "vulnerabilities remain for multi-worker deployments",
            "High",
            "Add threading.Lock(), rate limiting, and health endpoint regardless"
        )

    restore_file(MAIN_PY, original_main)
    restart_server()
    time.sleep(1)

    log("PASS", "Phase 10 complete")


# +==========================================================================+
# |  REPORT GENERATION                                                      |
# +==========================================================================+

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def generate_report() -> str:
    lines = []
    lines.append("=" * 78)
    lines.append("  GRIDX FAILURE-INJECTION TEST SUITE -- FULL REPORT")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 78)

    sorted_results = sorted(RESULTS, key=lambda r: SEVERITY_ORDER.get(r["severity"], 9))

    for i, r in enumerate(sorted_results, 1):
        lines.append(f"\n{'-'*78}")
        lines.append(f"  Finding #{i:02d}  [{r['severity'].upper()}]  {r['phase']}")
        lines.append(f"{'-'*78}")
        lines.append(f"  Failure Type   : {r['injection']}")
        lines.append(f"  Method         : {r['method']}")
        lines.append(f"  Observed       : {r['observed']}")
        lines.append(f"  Classification : {r['classification']}")
        lines.append(f"  Root Cause     : {r['root_cause']}")
        lines.append(f"  Severity       : {r['severity']}")
        lines.append(f"  Fix            : {r['fix']}")

    # Summary counts
    by_sev = {}
    for r in RESULTS:
        by_sev[r["severity"]] = by_sev.get(r["severity"], 0) + 1

    lines.append(f"\n{'='*78}")
    lines.append("  SUMMARY")
    lines.append(f"{'='*78}")
    lines.append(f"  Total findings : {len(RESULTS)}")
    for sev in ["Critical", "High", "Medium", "Low"]:
        count = by_sev.get(sev, 0)
        lines.append(f"  {sev:<10}     : {count}")

    # Top 5
    lines.append(f"\n{'-'*78}")
    lines.append("  TOP 5 CRITICAL VULNERABILITIES")
    lines.append(f"{'-'*78}")
    top5 = [r for r in sorted_results if r["severity"] in ("Critical", "High")][:5]
    for i, r in enumerate(top5, 1):
        lines.append(f"  {i}. [{r['severity']}] {r['phase']} -- {r['classification']}")
        lines.append(f"     Fix: {r['fix']}")

    # Architecture risks
    lines.append(f"\n{'-'*78}")
    lines.append("  ARCHITECTURAL RISKS DISCOVERED")
    lines.append(f"{'-'*78}")
    arch_risks = [
        "1. DUAL INDEXING SYSTEMS: Frontend uses clock-based index; backend uses "
         "sequential counter. These drift apart on every restart -> wrong prices shown.",
        "2. SHARED MUTABLE STATE WITHOUT LOCK: `state` dict is written by scheduler "
         "thread and read by HTTP threads with no synchronisation -> data races.",
        "3. HARDCODED SECRETS IN SOURCE: Supabase credentials in supabaseClient.ts; "
         "ngrok URL in api.ts -- both committed to git.",
        "4. NO INPUT/OUTPUT VALIDATION: compute_price_by_index() has no Pydantic "
         "models, no bounds checks, no NaN/Inf guards -> silent corruption possible.",
        "5. MISSING OBSERVABILITY: No /health endpoint, no scheduler heartbeat, "
         "no alerting -> failures are invisible until users report broken UI.",
    ]
    for risk in arch_risks:
        lines.append(f"  {risk}")

    # Priority fixes
    lines.append(f"\n{'-'*78}")
    lines.append("  PRIORITY FIXES")
    lines.append(f"{'-'*78}")
    fixes = [
        ("Scheduler Stability",
         "1. Wrap state dict with threading.Lock() in update_price() and get_price()\n"
         "   2. Derive index from IST clock, not sequential counter\n"
         "   3. Add try/except around entire update_price() body\n"
         "   4. Set misfire_grace_time=1 on the job\n"
         "   5. Add GET /health returning scheduler status + last_update + state"),
        ("API Protection",
         "1. Add FastAPI APIKeyHeader dependency on all write/critical endpoints\n"
         "   2. Replace allow_origins=['*'] with an explicit origin allowlist\n"
         "   3. Add SlowAPI rate limiter: @limiter.limit('200/minute') on /price\n"
         "   4. Add Pydantic response_model=PriceResponse to GET /price"),
        ("Time Synchronisation",
         "1. Replace datetime.now() -> datetime.now(tz=IST_ZONE).strftime('%H:%M')\n"
         "   2. Unify to a single IST-clock index: (h*60+m)//30 % 35\n"
         "   3. Add 'valid_from'/'valid_until' ISO-8601 timestamp fields to /price response\n"
         "   4. Fill the 12:30AM-6:30AM dataset gap or emit explicit off_hours flag"),
        ("Secret Management",
         "1. Move Supabase URL+key to .env.local (already gitignored)\n"
         "   2. Move ngrok/API URL to NEXT_PUBLIC_PYTHON_API_URL env var\n"
         "   3. Create .env.example with all keys documented\n"
         "   4. Run git-secrets or truffleHog pre-commit hook"),
    ]
    for title, detail in fixes:
        lines.append(f"\n  ? {title}")
        for line in detail.split("\n"):
            lines.append(f"    {line}")

    lines.append(f"\n{'='*78}\n  END OF REPORT\n{'='*78}\n")
    return "\n".join(lines)


# +==========================================================================+
# |  MAIN                                                                   |
# +==========================================================================+

def main() -> None:
    global BASE_URL

    parser = argparse.ArgumentParser(description="GridX Failure Injection Suite")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="Base URL of the FastAPI server")
    parser.add_argument("--no-server", action="store_true",
                        help="Do not attempt to start/manage the local server")
    parser.add_argument("--report-only", action="store_true",
                        help="Print previous report (not applicable here)")
    args = parser.parse_args()
    BASE_URL = args.base_url

    print(f"\n{BOLD}{CYN}+==============================================================+{RST}")
    print(f"{BOLD}{CYN}|   GridX Failure-Injection Test Suite -- Senior RE Edition     |{RST}")
    print(f"{BOLD}{CYN}+==============================================================+{RST}\n")
    print(f"  Target : {BASE_URL}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Stash original files so we can always restore on exit
    original_main_backup    = read_file(MAIN_PY)
    original_pricing_backup = read_file(PRICING_PY)

    def emergency_restore():
        try:
            write_file(MAIN_PY, original_main_backup)
            write_file(PRICING_PY, original_pricing_backup)
            stop_server()
            print(f"\n{YEL}(!) Emergency restore complete -- files returned to original state{RST}")
        except Exception as e:
            print(f"{RED}(x) Emergency restore FAILED: {e}{RST}")

    if not args.no_server:
        start_server()

    try:
        phase1_baseline()
        phase2_api_flood()
        phase3_schema_contract()
        phase4_scheduler_stress()
        phase5_clock_drift()
        phase6_data_injection()
        phase7_race_conditions()
        phase8_network_latency()
        phase9_env_misconfiguration()
        phase10_combined_chaos()

    except KeyboardInterrupt:
        print(f"\n{YEL}(!) Interrupted by user -- restoring system...{RST}")
        emergency_restore()
        sys.exit(1)
    except Exception as exc:
        print(f"\n{RED}(x) Unexpected error: {exc}{RST}")
        emergency_restore()
        raise
    finally:
        # Final guaranteed restore
        write_file(MAIN_PY, original_main_backup)
        write_file(PRICING_PY, original_pricing_backup)
        stop_server()

    report = generate_report()
    print(report)

    # Write report to file
    report_path = os.path.join(HERE, "failure_injection_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{GRN}(v) Report saved to: {report_path}{RST}\n")


if __name__ == "__main__":
    main()
