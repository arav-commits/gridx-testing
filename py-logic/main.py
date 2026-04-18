# main.py  ←  PURE TERMINAL DEMO

from price_data import DATA, compute_price_by_index, get_dataset_length
import time

print("🚀 Dynamic Pricing Console Demo Started")
print("→ New price every 10 seconds")
print("→ Full 48 time slots cycling")
print("→ Press Ctrl + C to stop\n")
print("=" * 70)

index = 0
total_slots = get_dataset_length()

while True:
    row = DATA[index]
    price = compute_price_by_index(index)

    if row["supply"] > row["demand"]:
        status = "SURPLUS ✅ (cheaper now)"
    elif row["demand"] > row["supply"]:
        status = "SHORTAGE ⚠️  (reduce usage)"
    else:
        status = "BALANCED"

    print(f"Time: {row['time']:>8}  |  Price: ₹{price:.2f}  |  {status}")

    index = (index + 1) % total_slots
    time.sleep(10)