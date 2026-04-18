# check_db.py — quick diagnostic script
import os, sys
from dotenv import load_dotenv
load_dotenv("../.env.local")
load_dotenv(".env")
from supabase import create_client

URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "https://jijcogmlrmiznurassuc.supabase.co"
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImppamNvZ21scm1pem51cmFzc3VjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjQ3NDQyMCwiZXhwIjoyMDkyMDUwNDIwfQ.eXVPuBzGsmqTVtRSfWejEtDAHRWv-HQGdAV34wrbj0c"

sb = create_client(URL, KEY)

print("=== dynamic_prices (latest 5) ===")
r1 = sb.table("dynamic_prices").select("*").order("created_at", desc=True).limit(5).execute()
print(f"  Row count: {len(r1.data)}")
for row in r1.data:
    print(f"  {row}")

print("\n=== users table (latest 5) ===")
try:
    r2 = sb.table("users").select("*").limit(5).execute()
    print(f"  Row count: {len(r2.data)}")
    for row in r2.data:
        print(f"  {row}")
except Exception as e:
    print(f"  ERROR reading users table: {e}")

print("\n=== price_logs table check ===")
try:
    r3 = sb.table("price_logs").select("*").limit(3).execute()
    print(f"  Row count: {len(r3.data)}")
    for row in r3.data:
        print(f"  {row}")
except Exception as e:
    print(f"  price_logs table does NOT exist or is inaccessible: {str(e)[:120]}")
