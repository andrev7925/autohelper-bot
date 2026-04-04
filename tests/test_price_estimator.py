import unittest
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from data_loader import load_baseline_data
from price_estimator import estimate_price
from handlers.buttons.analyze_ad import _merge_site_data, _has_minimum_analysis_data
from PIL import Image
from ai_core.engines.preview_engine import run_preview_engine
from ai_core.engines.pro_engine import run_pro_engine
from ai_core.engines.provin_engine import run_provin_engine
from ai_core.pipeline.pipeline import run_analysis_pipeline
from image_ad_parser import analyze_ad_from_images, normalize_plate, is_valid_irish_plate


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

    def test_minimum_analysis_data_does_not_require_price(self):
        self.assertTrue(
            _has_minimum_analysis_data(
                {
                    "make": "Toyota",
                    "model": "Corolla",
                    "price": None,
                    "estimated_price": None,
                    "estimated_market_price": None,
                }
            )
        )

    def test_merge_site_data_market_validates_weak_price_candidate(self):
        base_data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2011,
            "mileage_km": 180000,
            "source": "preview_batch",
        }
        extra_data = {
            "source": "telegram_text",
            "text": "Cork\n2100",
        }

        with patch(
            "handlers.buttons.analyze_ad.enrich_with_price_estimate",
            return_value={
                "estimated_market_price": 3000,
                "price_estimation_confidence": "medium",
            },
        ):
            merged = _merge_site_data(base_data, extra_data)

        self.assertEqual(merged.get("price"), 2100)
        self.assertEqual(merged.get("price_source"), "market_validated")
        self.assertTrue(merged.get("price_inferred"))

    def test_merge_site_data_does_not_override_explicit_price(self):
        base_data = {
            "make": "Nissan",
            "model": "Qashqai",
            "price": 4500,
            "currency": "EUR",
            "source": "url",
        }
        extra_data = {
            "source": "telegram_text",
            "text": "Cork\n2100",
        }

        merged = _merge_site_data(base_data, extra_data)

        self.assertEqual(merged.get("price"), 4500)
        self.assertFalse(bool(merged.get("price_inferred")))

    def test_merge_site_data_uses_heuristic_fallback_when_estimator_missing(self):
        base_data = {
            "make": "Nissan",
            "model": "Qashqai",
            "source": "preview_batch",
        }
        extra_data = {
            "source": "telegram_text",
            "text": "Cork\n2100",
        }

        with patch(
            "handlers.buttons.analyze_ad.enrich_with_price_estimate",
            return_value={
                "estimated_market_price": None,
                "price_estimation_confidence": "low",
            },
        ):
            merged = _merge_site_data(base_data, extra_data)

        self.assertEqual(merged.get("price"), 2100)
        self.assertEqual(merged.get("price_source"), "heuristic_fallback")
        self.assertTrue(merged.get("price_inferred"))

    def test_merge_site_data_multi_number_selects_market_nearest_price(self):
        base_data = {
            "make": "Kia",
            "model": "Rio",
            "source": "preview_batch",
        }
        extra_data = {
            "source": "telegram_text",
            "text": "Kia Rio 2011\n246000 km\nNCT 07-26\n2100",
        }

        with patch(
            "handlers.buttons.analyze_ad.enrich_with_price_estimate",
            return_value={
                "estimated_market_price": 3000,
                "price_estimation_confidence": "medium",
            },
        ):
            merged = _merge_site_data(base_data, extra_data)

        self.assertEqual(merged.get("price"), 2100)
        self.assertEqual(merged.get("price_source"), "multi_number_market_validated")
        self.assertTrue(merged.get("price_inferred"))


class PriceEstimatorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def _run_preview_capture(self, normalized_data, language="en", disable_enrichment=False):
        captured = {}

        def fake_build_preview_prompt(**kwargs):
            captured.update(kwargs)
            return "PROMPT"

        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="preview ok"))]
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=fake_response)))
        )

        patchers = [
            patch("ai_core.engines.preview_engine.build_preview_prompt", side_effect=fake_build_preview_prompt),
            patch("ai_core.engines.preview_engine.openai.AsyncOpenAI", return_value=fake_client),
            patch("ai_core.engines.preview_engine.print"),
        ]
        if disable_enrichment:
            patchers.append(
                patch(
                    "ai_core.engines.preview_engine.enrich_with_price_estimate",
                    side_effect=lambda data: dict(data),
                )
            )

        with patchers[0], patchers[1], patchers[2]:
            if disable_enrichment:
                with patchers[3]:
                    await run_preview_engine(
                        normalized_data=dict(normalized_data),
                        market_context={"country": "Ireland", "currency": "EUR", "avg_mileage_per_year": 15000},
                        language=language,
                    )
            else:
                await run_preview_engine(
                    normalized_data=dict(normalized_data),
                    market_context={"country": "Ireland", "currency": "EUR", "avg_mileage_per_year": 15000},
                    language=language,
                )

        return captured

    def test_irish_plate_validation_supports_two_letter_county(self):
        plate = normalize_plate("10MH12345")
        self.assertEqual(plate, "10-MH-12345")
        self.assertTrue(is_valid_irish_plate(plate))

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
        fake_gpt = AsyncMock(return_value="pro fallback")
        fake_analyze = MagicMock(return_value={"verdict": "good", "currency": "EUR"})
        fake_generate = MagicMock(return_value="pro ok")

        with patch("ai_core.engines.pro_engine.gpt_full_analysis_4o", fake_gpt), \
             patch("ai_core.engines.pro_engine.analyze_car", fake_analyze), \
             patch("ai_core.engines.pro_engine.generate_response", fake_generate):
            await run_pro_engine(
                input_data=dict(sample_car),
                normalized_data=dict(sample_car),
                market_context={"country": "Ireland", "currency": "EUR"},
                language="en",
            )

        payload = fake_analyze.call_args.args[0]
        self.assertIn("estimated_price", payload)
        self.assertTrue("confidence" in payload or "price_estimation_confidence" in payload)
        self.assertIn("price_estimation_explanation", payload)
        self.assertIsInstance(payload["estimated_price"], int)
        fake_gpt.assert_not_awaited()

    async def test_vin_contains_price(self):
        fake_gpt = AsyncMock(return_value="vin fallback")
        fake_analyze = MagicMock(return_value={"verdict": "good", "currency": "EUR"})
        fake_generate = MagicMock(return_value="vin ok")

        with patch("ai_core.engines.provin_engine.gpt_full_analysis_4o", fake_gpt), \
             patch("ai_core.engines.provin_engine.analyze_car", fake_analyze), \
             patch("ai_core.engines.provin_engine.generate_response", fake_generate):
            await run_provin_engine(
                input_data=dict(sample_car),
                normalized_data=dict(sample_car),
                market_context={"country": "Ireland", "currency": "EUR"},
                language="en",
            )

        payload = fake_analyze.call_args.args[0]
        self.assertIn("estimated_price", payload)
        self.assertIsInstance(payload["estimated_price"], int)
        self.assertIn("price_estimation_explanation", payload)
        fake_gpt.assert_not_awaited()

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

    async def test_photo_merge_pipeline_preview_keeps_explicit_miles(self):
        photo_data = {
            "make": "Nissan",
            "model": "Qashqai",
            "visual_make": "Nissan",
            "visual_model": "Qashqai",
            "visual_confidence": 0.9,
            "make_model_source": "vision_batch",
            "plate_number": None,
            "license_plate": "",
            "plate_confidence": 0.0,
            "plate_year": 2010,
            "registration_year": None,
            "year_mismatch": False,
            "import_suspected": False,
            "year": 2010,
            "year_source": "plate_inferred",
            "inspection_valid_until": "",
            "registration_date": "",
            "vin": "",
            "mileage": 230072,
            "mileage_km": 230072,
            "mileage_miles": None,
            "mileage_unit": "km",
            "country": "Ireland",
            "source": "preview_batch",
        }
        text_data = {
            "source": "telegram_text",
            "text": "Пробег: 230,000 миль (в основном трасса)\nЦена: 2900€",
            "title": "Nissan Qashqai +2",
            "brand_model": "Nissan Qashqai +2",
            "price": "2900",
            "currency": "EUR",
            "mileage": "230000",
            "mileage_miles": "230000",
            "mileage_km": "370148",
            "mileage_unit": "miles",
            "fuel_type": "diesel",
            "year": "2011",
        }
        merged = _merge_site_data(photo_data, text_data)

        async def fake_create(*args, **kwargs):
            prompt = kwargs["messages"][1]["content"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=prompt))]
            )

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=fake_create)))
        )

        with patch("ai_core.engines.preview_engine.openai.AsyncOpenAI", return_value=fake_client), \
             patch("ai_core.engines.preview_engine.print"), \
             patch("ai_core.pipeline.pipeline.print"):
            preview_text = await run_analysis_pipeline(merged, country="Ireland", mode="preview", language="en")

        self.assertIn("230,000 miles", preview_text)
        self.assertIn("370,148 km", preview_text)
        self.assertNotIn("230,072 km", preview_text)
        self.assertIn("🚨 Verdict:", preview_text)

    async def test_preview_keeps_price_message_independent_when_year_is_missing(self):
        merged = {
            "make": "Nissan",
            "model": "Qashqai +2",
            "price": "2900",
            "currency": "EUR",
            "mileage": 230000,
            "mileage_km": 370148,
            "mileage_miles": 230000,
            "mileage_unit": "miles",
            "fuel_type": "diesel",
            "year": None,
            "year_source": "unknown",
            "country": "Ireland",
            "text": "Nissan Qashqai +2\nПробег: 230,000 миль\nЦена: 2900€",
        }

        async def fake_create(*args, **kwargs):
            prompt = kwargs["messages"][1]["content"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=prompt))]
            )

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=fake_create)))
        )

        with patch("ai_core.engines.preview_engine.openai.AsyncOpenAI", return_value=fake_client), \
             patch("ai_core.engines.preview_engine.print"), \
             patch("ai_core.pipeline.pipeline.print"):
            preview_text = await run_analysis_pipeline(merged, country="Ireland", mode="preview", language="en")

        self.assertIn("🚨 Verdict:", preview_text)
        self.assertIn("📊 Market check:", preview_text)
        self.assertIn("👉 Decision:", preview_text)

    async def test_deal_signal_matrix_case_a_low_confidence(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": None,
            "price": 2900,
            "mileage": None,
            "estimated_market_price": None,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }
        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)
        self.assertEqual(captured["vehicle_data"]["data_confidence"], "low")
        self.assertEqual(captured["vehicle_data"]["data_confidence_level"], "low")
        self.assertIn("price evaluation is limited due to missing key data", captured["deal_text"])

    async def test_deal_signal_matrix_case_b_medium_confidence(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2010,
            "price": 2900,
            "mileage": None,
            "estimated_market_price": 7000,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }
        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)
        self.assertEqual(captured["vehicle_data"]["data_confidence"], "medium")

    async def test_deal_signal_matrix_case_c_high_confidence(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2010,
            "price": 2900,
            "mileage": 230000,
            "mileage_km": 370148,
            "mileage_unit": "miles",
            "mileage_miles": 230000,
            "estimated_market_price": 7000,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }
        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)
        self.assertEqual(captured["vehicle_data"]["data_confidence"], "high")

    async def test_deal_signal_matrix_case_d_below_market(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2010,
            "price": 5000,
            "mileage": 180000,
            "mileage_km": 180000,
            "estimated_market_price": 7000,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }
        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)
        self.assertEqual(captured["vehicle_data"]["price_position"], "below")
        self.assertIn("price looks favorable relative to the market", captured["deal_text"])

    async def test_deal_signal_matrix_case_e_above_market(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2010,
            "price": 9000,
            "mileage": 180000,
            "mileage_km": 180000,
            "estimated_market_price": 7000,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }
        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)
        self.assertEqual(captured["vehicle_data"]["price_position"], "above")
        self.assertIn("price looks overpriced relative to the market", captured["deal_text"])

    async def test_high_risk_caps_deal_score_and_ui_score(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2010,
            "price": 5000,
            "mileage": 370148,
            "mileage_km": 370148,
            "estimated_market_price": 7000,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }

        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)

        self.assertEqual(captured["vehicle_data"]["ownership_risk"], "high")
        self.assertEqual(captured["vehicle_data"]["deal_label"], "risky_deal")
        self.assertLessEqual(float(captured["score_value"]), 6.0)

    async def test_cheap_low_risk_can_stay_high_score(self):
        data = {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2020,
            "price": 15000,
            "mileage": 50000,
            "mileage_km": 50000,
            "estimated_market_price": 17000,
            "currency": "EUR",
            "fuel_type": "petrol",
            "country": "Ireland",
        }

        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)

        self.assertEqual(captured["vehicle_data"]["ownership_risk"], "low")
        self.assertGreaterEqual(float(captured["score_value"]), 8.0)

    async def test_preview_no_price_still_runs_and_marks_deal_unavailable(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2016,
            "price": None,
            "mileage": 180000,
            "mileage_km": 180000,
            "estimated_market_price": 7000,
            "estimated_market_min": 6200,
            "estimated_market_max": 7600,
            "currency": "EUR",
            "fuel_type": "diesel",
            "country": "Ireland",
        }

        captured = await self._run_preview_capture(data, language="en", disable_enrichment=True)

        self.assertFalse(captured["vehicle_data"]["price_available"])
        self.assertIn("cannot evaluate deal fairness without price", captured["deal_text"])

        async def fake_create(*args, **kwargs):
            prompt = kwargs["messages"][1]["content"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=prompt))]
            )

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=fake_create)))
        )

        with patch("ai_core.engines.preview_engine.openai.AsyncOpenAI", return_value=fake_client), \
             patch("ai_core.engines.preview_engine.print"):
            preview_text = await run_preview_engine(
                normalized_data=dict(data),
                market_context={"country": "Ireland", "currency": "EUR", "avg_mileage_per_year": 15000},
                language="en",
            )

        self.assertIn("Price: not specified", preview_text)
        self.assertIn("cannot evaluate deal fairness without price", preview_text)

    async def test_preview_recovers_irish_year_from_plate_ocr_fallback(self):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color=(255, 255, 255)).save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        fake_batch_result = {
            "make": "Nissan",
            "model": "Qashqai",
            "visual_confidence": 0.9,
            "plate_number": "",
            "plate_year": None,
            "registration_year": None,
            "year": None,
            "mileage": 230072,
            "mileage_unit": "km",
        }

        with patch("image_ad_parser.gpt4v_extract_preview_batch", return_value=fake_batch_result), \
             patch("image_ad_parser.extract_plate_paddle", return_value="10D12345"):
            result = await analyze_ad_from_images(
                [image_bytes],
                user_lang="uk",
                market_context={"country": "Ireland", "currency": "EUR"},
                processing_mode="preview",
            )

        self.assertEqual(result[0]["plate_number"], "10-D-12345")
        self.assertEqual(result[0]["plate_year"], 2010)
        self.assertEqual(result[0]["year"], 2010)
        self.assertEqual(result[0]["year_source"], "plate_inferred")

    async def test_preview_recovers_irish_year_when_paddle_fails_and_vision_fallback_succeeds(self):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color=(255, 255, 255)).save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        fake_batch_result = {
            "make": "Nissan",
            "model": "Qashqai",
            "visual_confidence": 0.9,
            "plate_number": "",
            "plate_year": None,
            "registration_year": None,
            "year": None,
            "mileage": 230072,
            "mileage_unit": "km",
        }

        with patch("image_ad_parser.gpt4v_extract_preview_batch", return_value=fake_batch_result), \
             patch("image_ad_parser.extract_plate_paddle", side_effect=RuntimeError("oneDNN failure")), \
             patch("image_ad_parser.gpt4v_extract_irish_plate_candidate", return_value="10-D-12345"):
            result = await analyze_ad_from_images(
                [image_bytes],
                user_lang="uk",
                market_context={"country": "Ireland", "currency": "EUR"},
                processing_mode="preview",
            )

        self.assertEqual(result[0]["plate_number"], "10-D-12345")
        self.assertEqual(result[0]["plate_year"], 2010)
        self.assertEqual(result[0]["year"], 2010)
        self.assertEqual(result[0]["year_source"], "plate_inferred")

    async def test_preview_recovers_irish_year_when_gpt_plate_response_is_not_json(self):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color=(255, 255, 255)).save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        fake_batch_result = {
            "make": "Nissan",
            "model": "Qashqai",
            "visual_confidence": 0.9,
            "plate_number": "",
            "plate_year": None,
            "registration_year": None,
            "year": None,
            "mileage": 230072,
            "mileage_unit": "km",
        }

        with patch("image_ad_parser.gpt4v_extract_preview_batch", return_value=fake_batch_result), \
             patch("image_ad_parser.extract_plate_paddle", side_effect=RuntimeError("oneDNN failure")), \
             patch("image_ad_parser.gpt4v_extract_irish_plate_candidate", return_value="10-MH-12345"):
            result = await analyze_ad_from_images(
                [image_bytes],
                user_lang="uk",
                market_context={"country": "Ireland", "currency": "EUR"},
                processing_mode="preview",
            )

        self.assertEqual(result[0]["plate_number"], "10-MH-12345")
        self.assertEqual(result[0]["plate_year"], 2010)
        self.assertEqual(result[0]["year"], 2010)


if __name__ == "__main__":
    unittest.main()
