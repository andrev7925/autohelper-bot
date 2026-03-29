import unittest

from data_loader import load_baseline_data
from price_estimator import estimate_price, estimate_price_range, enrich_with_price_estimate


class PriceEstimatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline_data = load_baseline_data()

    def test_exact_match_returns_high_confidence(self):
        car = {
            "make": "Volkswagen",
            "model": "Golf",
            "fuel": "Diesel",
            "transmission": "Manual",
            "year": 2015,
            "mileage": 185000,
            "body_type": "Hatchback",
        }

        result = estimate_price(car, self.baseline_data)

        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["source"], "exact")
        self.assertGreater(result["price"], 0)

    def test_model_match_returns_medium_confidence(self):
        car = {
            "make": "Volkswagen",
            "model": "Golf",
            "fuel": "Electric",
            "transmission": "Automatic",
            "year": 2015,
            "mileage": 185000,
        }

        result = estimate_price(car, self.baseline_data)

        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(result["source"], "model")
        self.assertGreater(result["price"], 0)

    def test_make_match_returns_low_confidence(self):
        car = {
            "make": "Toyota",
            "model": "Avensis",
            "fuel": "Diesel",
            "transmission": "Automatic",
            "year": 2014,
            "mileage": 210000,
        }

        result = estimate_price(car, self.baseline_data)

        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["source"], "make")
        self.assertGreater(result["price"], 0)

    def test_global_fallback_never_returns_none(self):
        car = {
            "make": "Unknown",
            "model": "Unknown",
            "fuel": "Unknown",
            "transmission": "Unknown",
            "year": 2014,
            "mileage": 150000,
        }

        result = estimate_price(car, [])

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["confidence"], "low")
        self.assertIsInstance(result["price"], int)
        self.assertGreater(result["price"], 0)

    def test_range_width_depends_on_confidence(self):
        high_range = estimate_price_range({"price": 10000, "confidence": "high"})
        low_range = estimate_price_range({"price": 10000, "confidence": "low"})

        self.assertLess(high_range[1] - high_range[0], low_range[1] - low_range[0])

    def test_enrich_with_price_estimate_adds_all_fields(self):
        car = {
            "make": "Volkswagen",
            "model": "Golf",
            "fuel_type": "Diesel",
            "transmission": "Manual",
            "year": 2015,
            "mileage": 185000,
        }

        enriched = enrich_with_price_estimate(car, self.baseline_data)

        self.assertIn("estimated_market_price", enriched)
        self.assertIn("estimated_market_min", enriched)
        self.assertIn("estimated_market_max", enriched)
        self.assertIn("price_estimation_confidence", enriched)
        self.assertIn("price_estimation_explanation", enriched)


if __name__ == "__main__":
    unittest.main()