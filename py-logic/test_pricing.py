import unittest
from pricing import compute_price_by_index, get_dataset_length, DATA

class TestPricing(unittest.TestCase):
    def test_get_dataset_length(self):
        self.assertEqual(get_dataset_length(), 35)
        
    def test_compute_price_by_index(self):
        # 0th element: demand=13.2, supply=8.0, pbase=8.04
        # dynamic_impact = 13.2 / 8.0 = 1.65
        # price = 8.04 + 1.65 + 0.50 = 10.19
        self.assertEqual(compute_price_by_index(0), 10.19)
        
    def test_compute_price_with_zero_supply(self):
        # Find or mock a 0 supply case to test if it handles it (it returns pb directly)
        DATA.append({"time": "Test", "demand": 10.0, "supply": 0, "pbase": 5.0})
        idx = len(DATA) - 1
        self.assertEqual(compute_price_by_index(idx), 5.0)
        DATA.pop()

if __name__ == '__main__':
    unittest.main()
