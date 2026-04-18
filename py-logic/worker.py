# worker.py

import time
from datetime import datetime, UTC
from price_data import compute_price_by_index, get_dataset_length, DATA
from supabase import create_client


SUPABASE_URL = "https://jijcogmlrmiznurassuc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImppamNvZ21scm1pem51cmFzc3VjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjQ3NDQyMCwiZXhwIjoyMDkyMDUwNDIwfQ.eXVPuBzGsmqTVtRSfWejEtDAHRWv-HQGdAV34wrbj0c"

# Create client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

index = 0
total_slots = get_dataset_length()


def push_price():
    global index

    row = DATA[index]
    price = compute_price_by_index(index)

    data = {
        "price": price,
        "demand": row["demand"],
        "supply": row["supply"],
        "created_at": datetime.now(UTC).isoformat()
    }

    # Insert into Supabase
    response = supabase.table("dynamic_prices").insert(data).execute()

    # Debug print
    print("Inserted:", data)
    print("Response:", response)

    index = (index + 1) % total_slots


def test_connection():
    try:
        res = supabase.table("dynamic_prices").select("*").limit(1).execute()
        print("✅ Supabase connection OK")
    except Exception as e:
        print("❌ Supabase connection failed:", e)
        exit(1)


if __name__ == "__main__":
    print("🚀 Worker started")

    # 🔍 First check connection
    test_connection()

    while True:
        try:
            push_price()
            print("⏳ Waiting 30 minutes...\n")
            time.sleep(1800)  # 30 minutes

        except Exception as e:
            print("❌ Error:", e)
            time.sleep(60)