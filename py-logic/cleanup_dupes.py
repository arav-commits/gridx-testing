# cleanup_dupes.py — removes duplicate rows in dynamic_prices, keeping only
# the row with the lowest id for each created_at timestamp.
import os
from dotenv import load_dotenv
load_dotenv("../.env.local")
load_dotenv(".env")
from supabase import create_client

URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "https://jijcogmlrmiznurassuc.supabase.co"
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImppamNvZ21scm1pem51cmFzc3VjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjQ3NDQyMCwiZXhwIjoyMDkyMDUwNDIwfQ.eXVPuBzGsmqTVtRSfWejEtDAHRWv-HQGdAV34wrbj0c"

sb = create_client(URL, KEY)

# Fetch all rows
rows = sb.table("dynamic_prices").select("id, created_at").order("id").execute()
print(f"Total rows before cleanup: {len(rows.data)}")

# Group by created_at
from collections import defaultdict
groups = defaultdict(list)
for row in rows.data:
    groups[row["created_at"]].append(row["id"])

# Delete duplicates (keep lowest id per timestamp)
deleted = 0
for ts, ids in groups.items():
    if len(ids) > 1:
        ids_to_delete = sorted(ids)[1:]  # keep the first, delete the rest
        for bad_id in ids_to_delete:
            sb.table("dynamic_prices").delete().eq("id", bad_id).execute()
            deleted += 1
            print(f"  Deleted duplicate id={bad_id} for {ts}")

print(f"\nDeleted {deleted} duplicate rows.")

# Verify
remaining = sb.table("dynamic_prices").select("id, created_at").order("created_at", desc=True).limit(10).execute()
print(f"Remaining rows (latest 10):")
for r in remaining.data:
    print(f"  id={r['id']}  created_at={r['created_at']}")
