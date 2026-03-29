import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from data_loader import load_baseline_data
from price_estimator import estimate_price
from ai_core.engines.preview_engine import run_preview_engine
from ai_core.engines.pro_engine import run_pro_engine
from ai_core.engines.provin_engine import run_provin_engine
from ai_core.pipeline.pipeline import run_analysis_pipeline


sample_car = {
    "make": "Volkswagen",
    "model": "Golf",
    "fuel": "Diesel",
    "fuel_type": "Diesel",
    "transmission": "Manual",
    "year": 2015,
    "mileage": 180000,
    "mileage_km": 180000,
    "body_type": "Hatchback",
    "country": "Ireland",
}


class PriceEstimatorStructureTests(unittest.TestCase):
    def test_estimator_returns_structure(self):
        baseline = load_baseline_data()
        result = estimate_price(sample_car, baseline)

        self.assertIn("price", result)
        self.assertIn("confidence", result)
        self.assertIn("explanation", result)

        self.assertIsInstance(result["price"], int)
        self.assertIn(result["confidence"], ["high", "medium", "low"])

    def test_unknown_model_fallback(self):
        unknown_car = {
            "make": "RandomBrand",
            "model": "UnknownModel",
            "fuel": "Petrol",
            "transmission": "Manual",
            "year": 2010,
            "mileage": 200000,
            "body_type": "Sedan",
        }

        baseline = load_baseline_data()
        result = estimate_price(unknown_car, baseline)

        self.assertGreater(result["price"], 0)
        self.assertEqual(result["confidence"], "low")


class PriceEstimatorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_contains_price(self):
        captured = {}

        def fake_build_preview_prompt(**kwargs):
            vehicle_data = kwargs["vehicle_data"]
            captured["estimated_price"] = vehicle_data.get("estimated_market_price")
            captured["price_confidence"] = vehicle_data.get("price_estimation_confidence")
            captured["price_explanation"] = vehicle_data.get("price_estimation_explanation")
            return "PROMPT"

        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="preview ok"))]
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=fake_response)))
        )

        with patch("ai_core.engines.preview_engine.build_preview_prompt", side_effect=fake_build_preview_prompt), \
             patch("ai_core.engines.preview_engine.openai.AsyncOpenAI", return_value=fake_client), \
             patch("ai_core.engines.preview_engine.print"):
            await run_preview_engine(
                normalized_data=dict(sample_car),
                market_context={"country": "Ireland", "currency": "EUR", "avg_mileage_per_year": 15000},
                language="en",
            )

        self.assertIn("estimated_price", captured)
        self.assertIn("price_confidence", captured)
        self.assertIn("price_explanation", captured)
        self.assertIsInstance(captured["estimated_price"], int)
        self.assertIn(captured["price_confidence"], ["high", "medium", "low"])
        self.assertTrue(captured["price_explanation"])

    async def test_pro_contains_price(self):
        fake_gpt = AsyncMock(return_value="pro ok")

        with patch("ai_core.engines.pro_engine.gpt_full_analysis_4o", fake_gpt):
            await run_pro_engine(
                input_data=dict(sample_car),
                normalized_data=dict(sample_car),
                market_context={"country": "Ireland", "currency": "EUR"},
                language="en",
            )

        payload = fake_gpt.await_args.args[0]
        self.assertIn("estimated_price", payload)
        self.assertTrue("confidence" in payload or "price_estimation_confidence" in payload)
        self.assertIn("price_estimation_explanation", payload)
        self.assertIsInstance(payload["estimated_price"], int)

    async def test_vin_contains_price(self):
        fake_gpt = AsyncMock(return_value="vin ok")

        with patch("ai_core.engines.provin_engine.gpt_full_analysis_4o", fake_gpt):
            await run_provin_engine(
                input_data=dict(sample_car),
                normalized_data=dict(sample_car),
                market_context={"country": "Ireland", "currency": "EUR"},
                language="en",
            )

        payload = fake_gpt.await_args.args[0]
        self.assertIn("estimated_price", payload)
        self.assertIsInstance(payload["estimated_price"], int)
        self.assertIn("price_estimation_explanation", payload)

    async def test_pipeline_modes_keep_price_enrichment(self):
        captured = {}

        async def fake_preview_engine(normalized_data, market_context, language):
            captured["preview"] = {
                "estimated_price": normalized_data.get("estimated_market_price"),
                "confidence": normalized_data.get("price_estimation_confidence"),
                "explanation": normalized_data.get("price_estimation_explanation"),
            }
            return "preview pipeline ok"

        async def fake_pro_engine(input_data, normalized_data, market_context, language):
            captured["pro"] = {
                "estimated_price": normalized_data.get("estimated_market_price"),
                "confidence": normalized_data.get("price_estimation_confidence"),
                "explanation": normalized_data.get("price_estimation_explanation"),
            }
            return "pro pipeline ok"

        async def fake_provin_engine(input_data, normalized_data, market_context, language):
            captured["provin"] = {
                "estimated_price": normalized_data.get("estimated_market_price"),
                "confidence": normalized_data.get("price_estimation_confidence"),
                "explanation": normalized_data.get("price_estimation_explanation"),
            }
            return "provin pipeline ok"

        with patch("ai_core.pipeline.pipeline.run_preview_engine", side_effect=fake_preview_engine), \
             patch("ai_core.pipeline.pipeline.run_pro_engine", side_effect=fake_pro_engine), \
             patch("ai_core.pipeline.pipeline.run_provin_engine", side_effect=fake_provin_engine), \
             patch("ai_core.pipeline.pipeline.print"):
            await run_analysis_pipeline(dict(sample_car), country="Ireland", mode="preview", language="en")
            await run_analysis_pipeline(dict(sample_car), country="Ireland", mode="pro", language="en")
            await run_analysis_pipeline(dict(sample_car), country="Ireland", mode="provin", language="en")

        for mode in ["preview", "pro", "provin"]:
            self.assertIn(mode, captured)
            self.assertIsInstance(captured[mode]["estimated_price"], int)
            self.assertGreater(captured[mode]["estimated_price"], 0)
            self.assertIn(captured[mode]["confidence"], ["high", "medium", "low"])
            self.assertTrue(captured[mode]["explanation"])


if __name__ == "__main__":
    unittest.main()
