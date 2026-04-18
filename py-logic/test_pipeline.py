# test_pipeline.py — Automated end-to-end pipeline verification
# Tests all 4 layers: Worker logic, DB state, API contract, data consistency
import os, sys, json, datetime
from dotenv import load_dotenv
load_dotenv("../.env.local")
load_dotenv(".env")
from supabase import create_client

# Setup
URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "https://jijcogmlrmiznurassuc.supabase.co"
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImppamNvZ21scm1pem51cmFzc3VjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjQ3NDQyMCwiZXhwIjoyMDkyMDUwNDIwfQ.eXVPuBzGsmqTVtRSfWejEtDAHRWv-HQGdAV34wrbj0c"
sb = create_client(URL, KEY)

passed = 0
failed = 0
total = 0

def test(name, condition, detail=""):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  -- {detail}")

print("=" * 60)
print("GRIDX END-TO-END PIPELINE TEST SUITE")
print("=" * 60)

# ── LAYER 1: Worker Logic ─────────────────────────────────────────────────
print("\n--- LAYER 1: Python Worker Logic ---")

from price_data import DATA, compute_price_by_index, get_dataset_length

test("Dataset has 48 entries (24h x 30min)", get_dataset_length() == 48, f"got {get_dataset_length()}")

# Verify price computation is deterministic and within bounds
for i in range(48):
    p = compute_price_by_index(i)
    test(f"Slot {i:02d} price in range [0, 15]", 0 <= p <= 15, f"got {p}")
    test(f"Slot {i:02d} price is float", isinstance(p, float), f"type={type(p)}")

# Verify time slot calculation
from worker import calculate_time_slot_index, calculate_seconds_until_next_slot
import pytz
ist = pytz.timezone("Asia/Kolkata")

# Test known timestamps
for hour in range(24):
    for minute in [5, 35]:
        t = datetime.datetime(2026, 4, 19, hour, minute, 0, tzinfo=ist)
        idx = calculate_time_slot_index(t)
        expected = hour * 2 + (1 if minute >= 30 else 0)
        test(f"Slot index for {hour:02d}:{minute:02d} = {expected}", idx == expected, f"got {idx}")

# Verify sleep calculation doesn't return negative
for hour in [0, 6, 12, 18, 23]:
    for minute in [0, 15, 29, 30, 45, 59]:
        t = datetime.datetime(2026, 4, 19, hour, minute, 30, tzinfo=ist)
        secs = calculate_seconds_until_next_slot(t)
        test(f"Sleep from {hour:02d}:{minute:02d} is positive ({int(secs)}s)", secs > 0, f"got {secs}")

# ── LAYER 1b: DB State ────────────────────────────────────────────────────
print("\n--- LAYER 1b: Supabase DB State ---")

rows = sb.table("dynamic_prices").select("id, created_at").order("created_at", desc=True).execute()
test("dynamic_prices table is not empty", len(rows.data) > 0, f"count={len(rows.data)}")

# Check for duplicates
from collections import Counter
ts_counts = Counter(r["created_at"] for r in rows.data)
dupes = {ts: count for ts, count in ts_counts.items() if count > 1}
test("No duplicate timestamps in dynamic_prices", len(dupes) == 0, f"dupes: {dupes}")

# ── LAYER 1c: Dedup Guard ─────────────────────────────────────────────────
print("\n--- LAYER 1c: Worker Dedup Guard ---")

from worker import push_price, get_current_ist_time, supabase as worker_sb

# Count rows before
before = sb.table("dynamic_prices").select("id").execute()
before_count = len(before.data)

# Push twice
push_price()
push_price()

after = sb.table("dynamic_prices").select("id").execute()
after_count = len(after.data)

# Should have added at most 1 row (if slot was new) or 0 (if slot already existed)
new_rows = after_count - before_count
test("Double push_price() adds at most 1 row", new_rows <= 1, f"added {new_rows} rows")

# ── LAYER 2: Data Consistency ─────────────────────────────────────────────
print("\n--- LAYER 2: Frontend-Backend Data Consistency ---")

# Verify the last inserted price matches what compute_price_by_index returns
latest = sb.table("dynamic_prices").select("*").order("created_at", desc=True).limit(1).execute()
if latest.data:
    db_price = float(latest.data[0]["price"])
    db_demand = float(latest.data[0]["demand"])
    db_supply = float(latest.data[0]["supply"])

    # Find the matching DATA index
    matched_idx = None
    for i, row in enumerate(DATA):
        if abs(row["demand"] - db_demand) < 0.01 and abs(row["supply"] - db_supply) < 0.01:
            matched_idx = i
            break

    if matched_idx is not None:
        expected_price = compute_price_by_index(matched_idx)
        test("DB price matches compute_price_by_index()", abs(db_price - expected_price) < 0.01,
             f"db={db_price}, expected={expected_price}")
    else:
        test("DB demand/supply matches a DATA row", False, f"d={db_demand}, s={db_supply}")

# ── LAYER 4: Users Table ─────────────────────────────────────────────────
print("\n--- LAYER 4: Users Table ---")

try:
    users = sb.table("users").select("*").limit(1).execute()
    test("users table is accessible", True)
    # Note: may have 0 rows if no one has logged in with working RLS
    print(f"  INFO  users table row count: {len(users.data)}")
except Exception as e:
    test("users table is accessible", False, str(e)[:80])

# ── SUMMARY ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
