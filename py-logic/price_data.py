
import math

MAX_PRICE = 15.0

DATA = [
    {"time": "12:00 AM", "demand": 9.6, "supply": 8.6, "pbase": 5.12},
    {"time": "12:30 AM", "demand": 9.4, "supply": 9.0, "pbase": 4.76},
    {"time": "1:00 AM", "demand": 9.8, "supply": 8.9, "pbase": 5.00},
    {"time": "1:30 AM", "demand": 10.1, "supply": 8.9, "pbase": 5.21},
    {"time": "2:00 AM", "demand": 10.3, "supply": 8.8, "pbase": 5.37},
    {"time": "2:30 AM", "demand": 10.4, "supply": 8.6, "pbase": 5.47},
    {"time": "3:00 AM", "demand": 10.5, "supply": 8.5, "pbase": 5.50},
    {"time": "3:30 AM", "demand": 10.4, "supply": 8.4, "pbase": 5.47},
    {"time": "4:00 AM", "demand": 10.3, "supply": 8.2, "pbase": 5.37},
    {"time": "4:30 AM", "demand": 10.1, "supply": 8.1, "pbase": 5.21},
    {"time": "5:00 AM", "demand": 9.8, "supply": 8.1, "pbase": 5.00},
    {"time": "5:30 AM", "demand": 9.4, "supply": 8.0, "pbase": 4.76},
    {"time": "6:00 AM", "demand": 10.5, "supply": 8.0, "pbase": 5.50},
    {"time": "6:30 AM", "demand": 11.0, "supply": 10.5, "pbase": 6.46},
    {"time": "7:00 AM", "demand": 13.2, "supply": 8.0, "pbase": 8.04},
    {"time": "7:30 AM", "demand": 12.0, "supply": 15.5, "pbase": 7.81},
    {"time": "8:00 AM", "demand": 12.5, "supply": 18.0, "pbase": 8.00},
    {"time": "8:30 AM", "demand": 13.0, "supply": 20.5, "pbase": 7.81},
    {"time": "9:00 AM", "demand": 13.5, "supply": 23.0, "pbase": 7.27},
    {"time": "9:30 AM", "demand": 14.0, "supply": 25.5, "pbase": 6.46},
    {"time": "10:00 AM", "demand": 11.5, "supply": 28.0, "pbase": 2.50},
    {"time": "10:30 AM", "demand": 12.1, "supply": 29.3, "pbase": 2.48},
    {"time": "11:00 AM", "demand": 12.8, "supply": 30.5, "pbase": 2.43},
    {"time": "11:30 AM", "demand": 13.3, "supply": 31.5, "pbase": 2.35},
    {"time": "12:00 PM", "demand": 12.2, "supply": 30.2, "pbase": 2.38},
    {"time": "12:30 PM", "demand": 13.9, "supply": 32.8, "pbase": 2.13},
    {"time": "1:00 PM", "demand": 14.0, "supply": 33.0, "pbase": 2.00},
    {"time": "1:30 PM", "demand": 13.9, "supply": 32.8, "pbase": 1.87},
    {"time": "2:00 PM", "demand": 13.7, "supply": 32.3, "pbase": 1.75},
    {"time": "2:30 PM", "demand": 13.3, "supply": 31.5, "pbase": 1.65},
    {"time": "3:00 PM", "demand": 12.8, "supply": 30.5, "pbase": 1.57},
    {"time": "3:30 PM", "demand": 12.1, "supply": 29.3, "pbase": 1.52},
    {"time": "4:00 PM", "demand": 13.0, "supply": 25.0, "pbase": 2.50},
    {"time": "4:30 PM", "demand": 13.6, "supply": 22.5, "pbase": 3.44},
    {"time": "5:00 PM", "demand": 14.2, "supply": 20.0, "pbase": 4.38},
    {"time": "5:30 PM", "demand": 14.9, "supply": 17.5, "pbase": 5.31},
    {"time": "6:00 PM", "demand": 15.5, "supply": 15.0, "pbase": 6.25},
    {"time": "6:30 PM", "demand": 16.1, "supply": 12.5, "pbase": 7.19},
    {"time": "7:00 PM", "demand": 18.0, "supply": 5.0, "pbase": 10.00},
    {"time": "7:30 PM", "demand": 17.4, "supply": 7.5, "pbase": 9.06},
    {"time": "8:00 PM", "demand": 18.0, "supply": 5.0, "pbase": 10.00},
    {"time": "8:30 PM", "demand": 16.9, "supply": 5.5, "pbase": 9.39},
    {"time": "9:00 PM", "demand": 15.9, "supply": 5.9, "pbase": 8.78},
    {"time": "9:30 PM", "demand": 14.8, "supply": 6.3, "pbase": 8.17},
    {"time": "10:00 PM", "demand": 13.8, "supply": 6.8, "pbase": 7.56},
    {"time": "10:30 PM", "demand": 12.8, "supply": 7.2, "pbase": 6.95},
    {"time": "11:00 PM", "demand": 11.7, "supply": 7.7, "pbase": 6.34},
    {"time": "11:30 PM", "demand": 10.6, "supply": 8.2, "pbase": 5.73},
]


def get_dataset_length():
    return len(DATA)


def compute_price_by_index(index: int):
    row = DATA[index]
    d = row["demand"]
    s = row["supply"]
    pb = row["pbase"]

    if s == 0:
        return pb

    dynamic_impact = d / s
    price = pb + dynamic_impact + 0.5

    return round(min(max(price, 0.0), MAX_PRICE), 2)
