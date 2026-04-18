import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import time

print("=== REAL-TIME ENERGY MARKET SIMULATION STARTED ===")
print("One row will be printed every 30 minutes (real delay)\n")

# Dataset
times = [
    "7:00 AM","7:30 AM","8:00 AM","8:30 AM","9:00 AM","9:30 AM","10:00 AM","10:30 AM",
    "11:00 AM","11:30 AM","12:00 PM","12:30 PM","1:00 PM","1:30 PM","2:00 PM","2:30 PM",
    "3:00 PM","3:30 PM","4:00 PM","4:30 PM","5:00 PM","5:30 PM","6:00 PM","6:30 PM",
    "7:00 PM","7:30 PM","8:00 PM","8:30 PM","9:00 PM","9:30 PM","10:00 PM","10:30 PM",
    "11:00 PM","11:30 PM","12:00 AM"
]

demand_gw = [13.2,10.7,10.6,12.0,13.6,11.8,11.2,10.6,11.8,12.1,12.2,11.3,11.4,12.9,
             12.2,12.2,12.9,11.0,12.5,13.8,14.3,15.5,17.4,18.0,18.0,17.5,17.0,16.8,
             16.5,14.0,12.5,11.0,10.2,9.8,9.6]

supply_gw = [8.0,13.4,19.8,21.3,24.5,25.2,28.4,29.6,30.0,30.6,30.2,31.6,33.2,32.8,
             28.0,23.5,21.9,19.5,15.0,12.0,11.2,9.0,6.0,5.5,5.0,4.9,4.8,4.8,4.8,6.5,
             8.0,9.0,9.5,9.0,8.6]

pbase = [8.04,3.41,2.38,3.07,3.17,2.88,2.46,2.16,2.37,2.38,2.38,1.97,1.96,2.36,2.46,
         3.07,3.28,3.18,5.50,7.20,8.14,9.10,10.00,10.00,10.00,10.00,10.00,10.00,10.00,
         9.00,7.50,6.80,6.53,5.80,5.12]

print("Time          Demand(GW)  Supply(GW)  Price(Rs/kWh)")
print("-" * 60)

for i in range(len(times)):
    d = demand_gw[i]
    s = supply_gw[i]
    pb = pbase[i]

    dynamic_impact = 1.0 * d / s
    price = pb + dynamic_impact + 0.50
    price = round(price, 2)

    print(f"{times[i]:12} {d:10.1f}    {s:10.1f}      {price:8.2f}")

    if i < len(times) - 1:
        print("   Waiting 30 minutes for next update...\n")
        time.sleep(5)   # 30 minutes real delay

# Save graph at the end
fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
axs[0].plot(times, demand_gw, color='blue', linewidth=2.5, marker='o')
axs[0].set_title('Demand Curve (GW)')
axs[0].set_ylabel('Demand (GW)')
axs[0].grid(True, alpha=0.3)

axs[1].plot(times, supply_gw, color='orange', linewidth=2.5, marker='o')
axs[1].set_title('Supply Curve (GW)')
axs[1].set_ylabel('Supply (GW)')
axs[1].grid(True, alpha=0.3)

axs[2].plot(times, [pb + (1.0*d/s) + 0.50 for d,s,pb in zip(demand_gw,supply_gw,pbase)], 
            color='green', linewidth=2.5, marker='o')
axs[2].set_title('Dynamic Customer Price (Rs/kWh)')
axs[2].set_ylabel('Price (Rs/kWh)')
axs[2].grid(True, alpha=0.3)
axs[2].set_xlabel('Time')

plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('energy_market_plot.png', dpi=250, bbox_inches='tight')

print("\nSimulation completed successfully!")