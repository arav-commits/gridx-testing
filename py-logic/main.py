from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from pricing import compute_price  # absolute import (same folder)

app = FastAPI()

# CORS (frontend will need this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔁 Simulated dataset (acts like real-time input)
DATASET = [
    {"time": "07:00", "demand": 120, "supply": 100},
    {"time": "07:30", "demand": 90, "supply": 110},
    {"time": "08:00", "demand": 140, "supply": 100},
]

# 🔄 State (stores latest computed price)
state = {
    "current_price": 3.80,
    "last_updated": None,
    "index": 0
}


# 🧠 Core updater (runs every 30 mins)
def update_price():
    global state

    data = DATASET[state["index"]]

    price = compute_price(data)

    state["current_price"] = price
    state["last_updated"] = datetime.now().strftime("%H:%M")
    
    print(f"[UPDATE] Time: {data['time']} | Price: ₹{price}")

    # move to next time slot (loop for demo)
    state["index"] = (state["index"] + 1) % len(DATASET)


# ⏱️ Scheduler (every 30 minutes)
scheduler = BackgroundScheduler()
scheduler.add_job(update_price, 'interval', minutes=30)
scheduler.start()


# 🌐 API endpoint
@app.get("/price")
def get_price():
    return {
        "value": state["current_price"],
        "last_updated": state["last_updated"]
    }