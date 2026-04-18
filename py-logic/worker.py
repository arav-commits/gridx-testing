# worker.py — GridX Price Engine
# Pushes computed electricity prices to Supabase `price_logs` every 30 minutes.
# ────────────────────────────────────────────────────────────────────────────────
# Design:
#   - Wall-clock-aligned: wakes at exactly HH:00 and HH:30 IST
#   - Idempotent: uses UPSERT on (slot_date, slot_index) — safe for restarts
#   - Backfills: on startup, fills any missing past slots for today
# ────────────────────────────────────────────────────────────────────────────────

import os
import time
import datetime
import pytz
from dotenv import load_dotenv

# Load env vars (try root .env.local first, then standard .env)
load_dotenv("../.env.local")
load_dotenv("../.env")
load_dotenv(".env")

from price_data import compute_price_by_index, DATA
from supabase import create_client

# ── Configuration ─────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ FATAL: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment.")
    print("   Set them in ../.env.local or as Docker env vars.")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
IST = pytz.timezone("Asia/Kolkata")

# ── Helpers ───────────────────────────────────────────────────────────────────

def now_ist() -> datetime.datetime:
    """Current time in IST, timezone-aware."""
    return datetime.datetime.now(IST)


def slot_index_from_time(dt: datetime.datetime) -> int:
    """
    Convert an IST datetime to a 0–47 slot index.
    00:00 → 0, 00:30 → 1, 01:00 → 2, …, 23:30 → 47
    """
    return dt.hour * 2 + (1 if dt.minute >= 30 else 0)


def slot_boundary(dt: datetime.datetime) -> datetime.datetime:
    """
    Round an IST datetime DOWN to its slot boundary.
    e.g. 04:17 → 04:00, 04:45 → 04:30
    """
    minute = 30 if dt.minute >= 30 else 0
    return dt.replace(minute=minute, second=0, microsecond=0)


def next_slot_boundary(dt: datetime.datetime) -> datetime.datetime:
    """
    Compute the NEXT slot boundary after `dt`.
    e.g. 04:17 → 04:30, 04:45 → 05:00
    """
    if dt.minute < 30:
        nxt = dt.replace(minute=30, second=0, microsecond=0)
    else:
        nxt = (dt.replace(minute=0, second=0, microsecond=0)
               + datetime.timedelta(hours=1))
    return nxt


def ist_date_today() -> datetime.date:
    """Current date in IST."""
    return now_ist().date()


def slot_to_utc_timestamp(date: datetime.date, index: int) -> str:
    """
    Convert (date, slot_index) to a UTC ISO timestamp string.
    e.g. (2026-04-19, 0) → IST 00:00 → UTC 18:30 previous day
    """
    hour = index // 2
    minute = (index % 2) * 30
    ist_dt = IST.localize(datetime.datetime(date.year, date.month, date.day, hour, minute, 0))
    utc_dt = ist_dt.astimezone(datetime.timezone.utc)
    return utc_dt.isoformat()


# ── Core: Upsert a single slot ───────────────────────────────────────────────

def upsert_slot(date: datetime.date, index: int) -> bool:
    """
    Compute and upsert a price for the given (date, slot_index).
    Uses ON CONFLICT (slot_date, slot_index) DO UPDATE — fully idempotent.
    Returns True on success, False on failure.
    """
    row = DATA[index]
    price = compute_price_by_index(index)
    slot_time_utc = slot_to_utc_timestamp(date, index)

    data = {
        "slot_date": date.isoformat(),
        "slot_index": index,
        "slot_time": slot_time_utc,
        "price": float(price),
        "demand": float(row["demand"]),
        "supply": float(row["supply"]),
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = (
                supabase.table("price_logs")
                .upsert(data, on_conflict="slot_date,slot_index")
                .execute()
            )
            return True
        except Exception as e:
            err = str(e)[:120]
            print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed: {err}")
            time.sleep(2 * (attempt + 1))

    return False


# ── Backfill: fill all past slots for today on startup ────────────────────────

def backfill_today():
    """
    On startup, ensure all past slots for today exist in the DB.
    This handles crash recovery — if the worker was down, past slots get filled.
    """
    today = ist_date_today()
    current = now_ist()
    current_index = slot_index_from_time(current)

    print(f"📋 Backfilling today ({today}) — slots 0 to {current_index}...")

    # Fetch which slots already exist for today
    try:
        existing = (
            supabase.table("price_logs")
            .select("slot_index")
            .eq("slot_date", today.isoformat())
            .execute()
        )
        existing_indices = set(r["slot_index"] for r in existing.data) if existing.data else set()
    except Exception as e:
        print(f"  ⚠️  Could not check existing slots: {str(e)[:100]}")
        existing_indices = set()

    filled = 0
    for idx in range(current_index + 1):  # Include current slot
        if idx not in existing_indices:
            ok = upsert_slot(today, idx)
            if ok:
                filled += 1
                label = DATA[idx]["time"]
                price = compute_price_by_index(idx)
                print(f"  ✅ Backfilled slot {idx} ({label}) → ₹{price}")
            else:
                print(f"  ❌ Failed to backfill slot {idx}")

    if filled == 0:
        print("  ℹ️  All past slots already exist. No backfill needed.")
    else:
        print(f"  📊 Backfilled {filled} missing slot(s).")


# ── Connection test ───────────────────────────────────────────────────────────

def test_connection():
    try:
        res = supabase.table("price_logs").select("id").limit(1).execute()
        print("✅ Supabase connection OK — price_logs table accessible")
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        print("   Make sure the price_logs table exists. Run the SQL migration first.")
        exit(1)


# ── Main loop: wall-clock-aligned execution ───────────────────────────────────

def wait_for_next_slot():
    """
    Block until the next HH:00 or HH:30 boundary.
    Uses a tight loop with 1-second sleeps for accuracy (no drift).
    """
    target = next_slot_boundary(now_ist())
    label = target.strftime("%I:%M %p")
    print(f"⏳ Waiting for next slot boundary: {label} IST...")

    while True:
        remaining = (target - now_ist()).total_seconds()
        if remaining <= 0:
            break
        # Sleep in smaller chunks to stay aligned
        time.sleep(min(remaining, 1.0))


def run_loop():
    """Main execution loop — push current slot, then wait for next boundary."""
    while True:
        try:
            current = now_ist()
            today = current.date()
            index = slot_index_from_time(current)
            label = DATA[index]["time"]
            price = compute_price_by_index(index)

            ok = upsert_slot(today, index)
            if ok:
                print(f"✅ [{current.strftime('%I:%M:%S %p')}] Pushed slot {index} ({label}) → ₹{price}")
            else:
                print(f"❌ [{current.strftime('%I:%M:%S %p')}] Failed to push slot {index}")

            # Wait for next slot boundary
            wait_for_next_slot()

        except Exception as e:
            print(f"❌ Loop error: {e}")
            # On error, sleep 30 seconds then retry (avoids rapid crash loops)
            time.sleep(30)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 GridX Price Worker — Starting...")
    print(f"   Time: {now_ist().strftime('%Y-%m-%d %I:%M:%S %p')} IST")
    print(f"   Supabase: {SUPABASE_URL}")
    print()

    test_connection()
    backfill_today()

    print()
    print("🔁 Entering main loop — will push prices at every HH:00 and HH:30...")
    print()

    run_loop()
