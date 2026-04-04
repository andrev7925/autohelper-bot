import unittest

from data_loader import load_baseline_data
from ai_core.pipeline.car_profile import get_car_profile
from price_estimator import describe_country_package, estimate_price, estimate_price_range, enrich_with_price_estimate
from ai_core.context.market_loader import get_context


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

    def test_ireland_dataset_is_used_for_ie_country(self):
        baseline = [
            {
                "make": "Nissan",
                "model": "Qashqai",
                "body_type": "SUV",
                "fuel": "Diesel",
                "transmission": "Manual",
                "year_from": 2011,
                "year_to": 2013,
                "median_price": 7200,
                "typical_mileage": 160000,
                "sample_size": 10,
                "country": "Germany",
            },
            {
                "make": "Nissan",
                "model": "Qashqai",
                "body_type": "SUV",
                "fuel": "Diesel",
                "transmission": "Manual",
                "year_from": 2011,
                "year_to": 2013,
                "median_price": 11200,
                "typical_mileage": 150000,
                "sample_size": 18,
                "country": "Ireland",
            },
        ]
        car = {
            "make": "Nissan",
            "model": "Qashqai",
            "fuel": "Diesel",
            "transmission": "Manual",
            "year": 2012,
            "mileage": 180000,
            "country": "IE",
        }

        result = estimate_price(car, baseline)

        self.assertEqual(result["source"], "exact")
        self.assertEqual(result["price_source"], "ireland_dataset")
        self.assertEqual(result["market_country_used"], "Ireland")
        self.assertGreater(result["general_price"], 9000)

    def test_high_mileage_segmentation_lowers_adjusted_price(self):
        car = {
            "make": "Nissan",
            "model": "Qashqai",
            "fuel": "Diesel",
            "transmission": "Manual",
            "year": 2012,
            "mileage_km": 274000,
            "country": "Ireland",
        }

        enriched = enrich_with_price_estimate(car, self.baseline_data)

        self.assertIn("general_market_range", enriched)
        self.assertIn("adjusted_market_range", enriched)
        self.assertLess(enriched["adjusted_market_max"], enriched["general_market_max"])
        self.assertLess(enriched["estimated_market_price"], enriched["general_market_price"])
        self.assertIn(enriched["mileage_segment"], {"low", "very_low"})

    def test_hard_cap_applies_for_250k_plus(self):
        car = {
            "make": "Nissan",
            "model": "Qashqai",
            "fuel": "Diesel",
            "transmission": "Manual",
            "year": 2012,
            "mileage_km": 255000,
            "country": "Ireland",
        }

        enriched = enrich_with_price_estimate(car, self.baseline_data)

        self.assertLessEqual(enriched["estimated_market_max"], 4000)
        self.assertLessEqual(enriched["estimated_market_min"], 3000)
        self.assertLessEqual(enriched["adjusted_market_max"], 4000)
        self.assertLessEqual(enriched["adjusted_market_min"], 3000)
        self.assertLessEqual(enriched["estimated_market_price"], 4000)

    def test_hard_cap_applies_for_270k_plus(self):
        car = {
            "make": "Nissan",
            "model": "Qashqai",
            "fuel": "Diesel",
            "transmission": "Manual",
            "year": 2012,
            "mileage_km": 274000,
            "country": "Ireland",
        }

        enriched = enrich_with_price_estimate(car, self.baseline_data)

        self.assertLessEqual(enriched["estimated_market_max"], 3500)
        self.assertLessEqual(enriched["estimated_market_min"], 2200)
        self.assertLessEqual(enriched["adjusted_market_max"], 3500)
        self.assertLessEqual(enriched["adjusted_market_min"], 2200)
        self.assertLessEqual(enriched["estimated_market_price"], 3500)

    def test_describe_country_package_ie(self):
        description = describe_country_package("IE")

        self.assertEqual(description["country"], "IE")
        self.assertEqual(description["data_used"], "ireland_dataset")
        self.assertEqual(description["currency"], "EUR")
        self.assertIn("Mileage segmentation", description["adjustments"])

    def test_market_loader_does_not_force_ireland_for_other_country(self):
        context = get_context("DE")

        self.assertEqual(context["country"], "DE")
        self.assertEqual(context["currency"], "EUR")

    def test_get_car_profile_for_bmw_5_series_diesel(self):
        profile = get_car_profile("BMW", "5 Series", "diesel")

        self.assertEqual(profile["segment"], "premium")
        self.assertEqual(profile["engine_type"], "diesel")
        self.assertEqual(profile["mileage_tolerance"], "high")

    def test_premium_profile_reduces_mileage_penalty_vs_budget_car(self):
        baseline = [
            {
                "make": "BMW",
                "model": "5 Series",
                "body_type": "Sedan",
                "fuel": "Diesel",
                "transmission": "Automatic",
                "year_from": 2014,
                "year_to": 2016,
                "median_price": 12000,
                "typical_mileage": 150000,
                "sample_size": 10,
                "country": "Ireland",
            },
            {
                "make": "Citroen",
                "model": "C5",
                "body_type": "Sedan",
                "fuel": "Petrol",
                "transmission": "Automatic",
                "year_from": 2014,
                "year_to": 2016,
                "median_price": 12000,
                "typical_mileage": 150000,
                "sample_size": 10,
                "country": "Ireland",
            },
        ]

        bmw_result = estimate_price(
            {
                "make": "BMW",
                "model": "5 Series",
                "fuel": "Diesel",
                "transmission": "Automatic",
                "year": 2015,
                "mileage_km": 280000,
                "country": "IE",
            },
            baseline,
        )
        citroen_result = estimate_price(
            {
                "make": "Citroen",
                "model": "C5",
                "fuel": "Petrol",
                "transmission": "Automatic",
                "year": 2015,
                "mileage_km": 280000,
                "country": "IE",
            },
            baseline,
        )

        self.assertGreater(bmw_result["price"], citroen_result["price"])


if __name__ == "__main__":
    unittest.main()