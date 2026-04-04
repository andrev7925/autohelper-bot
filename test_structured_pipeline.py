import unittest
from unittest.mock import patch

from ai_core.pipeline.structured_pipeline import (
    analyze_car,
    build_response_system_prompt,
    build_analysis_user_prompt,
    generate_response,
    get_market_baseline,
    normalize_input,
    run_structured_preview_pipeline,
    validate_language,
)


class StructuredPipelineTests(unittest.IsolatedAsyncioTestCase):
    def test_normalize_input_extracts_core_fields(self):
        raw = "Kia Rio 2011\n246000 km\nPrice: 2.5k EUR\nmanual diesel"
        data = normalize_input(raw)

        self.assertEqual(data["make"], "Kia")
        self.assertEqual(data["model"], "Rio")
        self.assertEqual(data["year"], 2011)
        self.assertEqual(data["price_eur"], 2500)
        self.assertEqual(data["mileage_km"], 246000)
        self.assertEqual(data["fuel"], "diesel")
        self.assertEqual(data["transmission"], "manual")

    def test_normalize_input_converts_miles_to_km(self):
        raw = "Toyota Corolla 2012\n120000 miles\n€4000"
        data = normalize_input(raw)
        self.assertEqual(data["price_eur"], 4000)
        self.assertEqual(data["mileage_km"], 193121)

    def test_normalize_input_ignores_service_km_and_corrects_shorthand(self):
        raw = "Skoda Octavia 2015\nTiming belt replaced 2000 km ago\nMileage 292 km\n€4500"
        data = normalize_input(raw)

        self.assertEqual(data["year"], 2015)
        self.assertEqual(data["mileage_km"], 292000)

    def test_normalize_input_keeps_real_low_mileage_for_recent_car(self):
        raw = "Tesla Model 3 2025\nMileage 292 km\n€31000"
        data = normalize_input(raw)

        self.assertEqual(data["year"], 2025)
        self.assertEqual(data["mileage_km"], 292)

    def test_analyze_car_returns_required_blocks(self):
        data = {
            "make": "Kia",
            "model": "Rio",
            "year": 2011,
            "price_eur": 2100,
            "mileage_km": 246000,
            "fuel": "diesel",
            "transmission": "manual",
        }
        analysis = analyze_car(data, context={"language": "en", "country": "IE"})

        self.assertIn("estimated_price_min", analysis)
        self.assertIn("estimated_price_max", analysis)
        self.assertIn(analysis["price_position"], {"low", "market", "high"})
        self.assertIn(analysis["mileage_evaluation"], {"normal", "high", "very_high", "critical"})
        self.assertIn(analysis["risk_score"], {"low", "medium", "high"})
        self.assertIn("expected_cost_min", analysis)
        self.assertIn("expected_cost_max", analysis)
        self.assertTrue(isinstance(analysis.get("key_insight"), str) and analysis.get("key_insight"))
        self.assertIn(analysis["verdict"], {"good", "questionable", "risky", "bad"})

    def test_generate_response_contains_required_sections(self):
        data = {
            "make": "Kia",
            "model": "Rio",
            "title": "Kia Rio 1.4 CRDi",
            "year": 2011,
            "price_eur": 2100,
            "mileage_km": 246000,
            "fuel": "diesel",
            "text": "Fresh service, no investment needed",
        }
        analysis = {
            "estimated_market_min": 2800,
            "estimated_market_max": 3900,
            "estimated_price_min": 2600,
            "estimated_price_max": 3200,
            "price_position": "low",
            "price_flag": "normal",
            "mileage_evaluation": "very_high",
            "risk_score": "high",
            "expected_cost_min": 1400,
            "expected_cost_max": 2600,
            "key_insight": "Low price now can mean high costs later.",
            "verdict": "risky",
        }

        text = generate_response(analysis, data, {"language": "en", "country": "IE"})
        self.assertIn("🚗", text)
        self.assertIn("🚨 Verdict:", text)
        self.assertIn("📊 Market check:", text)
        self.assertIn("overall range", text)
        self.assertIn("for this mileage", text)
        self.assertIn("💸", text)
        self.assertIn("⚠️ Risk:", text)
        self.assertIn("💣 Key insight:", text)
        self.assertIn("❗ Important:", text)
        self.assertIn("🧠 What is suspicious:", text)
        self.assertIn("🔍 Check before buying:", text)
        self.assertIn("💡 Simple conclusion:", text)
        self.assertIn("👉 Decision:", text)

    async def test_structured_preview_uses_trusted_price_not_year(self):
        input_data = {
            "make": "Vauxhall",
            "model": "Insignia",
            "title": "Opel Insignia 2.0 Diesel",
            "brand_model": "Opel Insignia 2.0 Diesel",
            "year": 2009,
            "price": 1500,
            "currency": "EUR",
            "mileage": 320000,
            "mileage_km": 320000,
            "fuel_type": "diesel",
            "country": "Ireland",
            "text": "Opel Insignia 2.0 Diesel\n2009 рік\nПробіг: 320 тис. км\nЦіна: 1500€\nбез вкладень",
            "estimated_market_min": 11138,
            "estimated_market_max": 18562,
            "price_estimation_confidence": "low",
            "price_estimation_source": "fallback",
        }

        result = await run_structured_preview_pipeline(input_data=input_data, language="en", country="Ірландія")

        self.assertIn("1500", result)
        self.assertNotIn("price 2009", result.lower())
        self.assertIn("Opel Insignia 2.0 Diesel", result)
        self.assertIn("Market check", result)

    def test_same_car_different_country_changes_market_range(self):
        data_ie = {
            "make": "Kia",
            "model": "Rio",
            "year": 2011,
            "price_eur": 2100,
            "mileage_km": 246000,
            "country": "IE",
        }
        data_ua = {
            "make": "Kia",
            "model": "Rio",
            "year": 2011,
            "price_eur": 2100,
            "mileage_km": 246000,
            "country": "UA",
        }

        ie = analyze_car(data_ie, context={"language": "uk", "country": "IE"})
        ua = analyze_car(data_ua, context={"language": "uk", "country": "UA"})

        self.assertNotEqual((ie["estimated_price_min"], ie["estimated_price_max"]), (ua["estimated_price_min"], ua["estimated_price_max"]))
        self.assertEqual(ie["currency"], "EUR")
        self.assertEqual(ua["currency"], "USD")

    def test_response_prompt_includes_language_country_currency(self):
        prompt = build_response_system_prompt(
            context={"language": "uk", "country": "UA"},
            currency="USD",
            allow_positive_tone=False,
            forbid_words=["надійний", "reliable"],
        )
        self.assertIn("You are NOT allowed to analyze the car.", prompt)
        self.assertIn("Analysis is already done.", prompt)
        self.assertIn("You MUST ONLY:", prompt)
        self.assertIn("DO NOT:", prompt)
        self.assertIn("change verdict", prompt)
        self.assertIn("allow_positive_tone = false", prompt)
        self.assertIn("надійний, reliable", prompt)
        self.assertIn("Market country: UA", prompt)
        self.assertIn("Language: uk", prompt)
        self.assertIn("Currency: USD.", prompt)

    def test_analysis_user_prompt_contains_user_language(self):
        prompt = build_analysis_user_prompt(
            raw_listing="Kia Rio 2011",
            country="IE",
            currency="EUR",
            language="uk",
        )
        self.assertIn("user_language: uk", prompt)

    def test_country_map_handles_localized_ireland_and_polska(self):
        base = {
            "make": "Kia",
            "model": "Rio",
            "year": 2011,
            "price_eur": 2100,
            "mileage_km": 246000,
        }
        ie = analyze_car(base, context={"language": "uk", "country": "Ірландія"})
        pl = analyze_car(base, context={"language": "pl", "country": "Polska"})
        self.assertEqual(ie["country"], "IE")
        self.assertEqual(pl["country"], "PL")
        self.assertEqual(pl["currency"], "PLN")

    def test_ireland_trusted_market_ranges_override_placeholder_fallback(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2012,
            "mileage_km": 274000,
            "country": "IE",
            "general_market_min": 5200,
            "general_market_max": 7400,
            "adjusted_market_min": 3100,
            "adjusted_market_max": 4300,
            "price_estimation_confidence": "low",
            "price_estimation_source": "model",
            "price_source": "ireland_dataset",
            "mileage_segment": "low",
        }

        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertEqual(analysis["estimated_market_min"], 5200)
        self.assertEqual(analysis["estimated_market_max"], 7400)
        self.assertEqual(analysis["estimated_price_min"], 2200)
        self.assertEqual(analysis["estimated_price_max"], 3500)

    def test_high_mileage_fallback_market_range_is_hard_capped(self):
        data = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2012,
            "mileage_km": 274000,
            "country": "IE",
        }

        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertLessEqual(analysis["estimated_price_max"], 3500)
        self.assertLessEqual(analysis["estimated_price_min"], 2200)

    def test_hard_rule_for_very_high_mileage_applies(self):
        data = {
            "make": "Kia",
            "model": "Rio",
            "year": 2011,
            "price_eur": 2100,
            "mileage_km": 320000,
        }
        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertEqual(analysis["risk_score"], "high")
        self.assertEqual(analysis["verdict"], "risky")
        self.assertGreaterEqual(int(analysis["expected_cost_min"]), 1000)
        self.assertGreaterEqual(int(analysis["expected_cost_max"]), 3000)
        self.assertEqual(
            analysis["key_insight"],
            "дуже великий пробіг — майже гарантовані витрати після покупки",
        )
        self.assertFalse(bool(analysis.get("allow_positive_tone", True)))

    def test_positive_tone_block_flags_for_high_mileage(self):
        data = {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2014,
            "price_eur": 5000,
            "mileage_km": 230000,
        }
        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertFalse(bool(analysis.get("allow_positive_tone", True)))
        forbid_words = analysis.get("forbid_words") or []
        self.assertIn("надійний", forbid_words)
        self.assertIn("хороший варіант", forbid_words)
        self.assertIn("good choice", forbid_words)
        self.assertIn("reliable", forbid_words)

    def test_mileage_over_220k_forces_medium_questionable(self):
        data = {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
            "price_eur": 6500,
            "mileage_km": 230500,
        }
        analysis = analyze_car(data, context={"language": "en", "country": "IE"})

        self.assertEqual(analysis["risk_score"], "medium")
        self.assertEqual(analysis["verdict"], "questionable")

    def test_suspicious_low_price_flags_risky(self):
        data = {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2018,
            "price_eur": 1000,
            "mileage_km": 120000,
        }
        analysis = analyze_car(data, context={"language": "en", "country": "IE"})

        self.assertEqual(analysis["price_flag"], "suspicious_low")
        self.assertEqual(analysis["verdict"], "risky")

    def test_diesel_high_mileage_increases_costs(self):
        data = {
            "make": "Volkswagen",
            "model": "Golf",
            "year": 2013,
            "price_eur": 4000,
            "mileage_km": 240000,
            "fuel": "diesel",
        }
        analysis = analyze_car(data, context={"language": "en", "country": "IE"})

        self.assertGreaterEqual(int(analysis["expected_cost_min"]), 900)
        self.assertGreaterEqual(int(analysis["expected_cost_max"]), 2000)

    def test_dpf_removed_adds_warning(self):
        data = {
            "make": "Volkswagen",
            "model": "Passat",
            "year": 2012,
            "price_eur": 3500,
            "mileage_km": 210000,
            "text": "Car in good condition, DPF removed recently",
        }
        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        warnings = analysis.get("warnings") or []
        self.assertTrue(any("DPF видалений" in item for item in warnings))

    def test_regression_cheap_320k_diesel_dpf_removed(self):
        data = {
            "make": "Volkswagen",
            "model": "Passat",
            "year": 2012,
            "price_eur": 1500,
            "mileage_km": 320000,
            "fuel": "diesel",
            "text": "DPF removed, cheap car",
        }
        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertEqual(analysis["verdict"], "risky")
        self.assertEqual(analysis["risk_score"], "high")
        self.assertEqual(analysis["price_flag"], "suspicious_low")
        self.assertGreaterEqual(int(analysis["expected_cost_min"]), 1300)
        self.assertGreaterEqual(int(analysis["expected_cost_max"]), 4000)
        self.assertFalse(bool(analysis.get("allow_positive_tone", True)))
        self.assertTrue(any("DPF видалений" in item for item in (analysis.get("warnings") or [])))

    def test_regression_cheap_price_forces_risky_even_with_mid_risk(self):
        data = {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2015,
            "price_eur": 1200,
            "mileage_km": 180000,
            "fuel": "petrol",
        }
        analysis = analyze_car(data, context={"language": "en", "country": "IE"})

        self.assertEqual(analysis["price_flag"], "suspicious_low")
        self.assertEqual(analysis["verdict"], "risky")

    def test_regression_230k_mileage_never_good(self):
        data = {
            "make": "Honda",
            "model": "Civic",
            "year": 2016,
            "price_eur": 5000,
            "mileage_km": 230000,
            "fuel": "petrol",
        }
        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertIn(analysis["verdict"], {"questionable", "risky"})
        self.assertFalse(bool(analysis.get("allow_positive_tone", True)))

    def test_regression_low_risk_case_can_be_good(self):
        data = {
            "make": "Toyota",
            "model": "Yaris",
            "year": 2020,
            "price_eur": 10500,
            "mileage_km": 65000,
            "fuel": "petrol",
        }
        analysis = analyze_car(data, context={"language": "en", "country": "IE"})

        self.assertEqual(analysis["risk_score"], "low")
        self.assertEqual(analysis["verdict"], "good")

    def test_bmw_diesel_high_mileage_uses_profile_tolerance(self):
        data = {
            "make": "BMW",
            "model": "5 Series",
            "year": 2015,
            "mileage_km": 280000,
            "fuel": "diesel",
            "country": "IE",
        }

        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})
        response = generate_response(analysis, data, {"language": "uk", "country": "IE"})

        self.assertNotEqual(analysis["risk_score"], "high")
        self.assertIn("вважається нормальним", analysis["risk_reason"])
        self.assertIn("дизельного BMW", response)

    def test_medium_tolerance_mileage_explanation_is_profile_aware(self):
        data = {
            "make": "Opel",
            "model": "Insignia",
            "year": 2014,
            "mileage_km": 230000,
            "fuel": "diesel",
            "country": "IE",
        }

        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertIn("пробіг вже підвищений, можливий знос", analysis["risk_reason"])

    def test_citroen_petrol_high_mileage_becomes_high_risk(self):
        data = {
            "make": "Citroen",
            "model": "C4",
            "year": 2014,
            "mileage_km": 210000,
            "fuel": "petrol",
            "country": "IE",
        }

        analysis = analyze_car(data, context={"language": "uk", "country": "IE"})

        self.assertEqual(analysis["risk_score"], "high")
        self.assertEqual(analysis["verdict"], "risky")
        self.assertIn("пробіг критичний для цього типу авто", analysis["risk_reason"])

    def test_regression_high_price_high_mileage_not_balanced(self):
        data = {
            "make": "Ford",
            "model": "C-Max",
            "year": 2007,
            "price_eur": 1450,
            "mileage_km": 294020,
            "fuel": "petrol",
            "text": "new nct, great condition, no investment needed, full service",
        }

        analysis = analyze_car(data, context={"language": "en", "country": "IE"})
        response = generate_response(analysis, data, {"language": "en", "country": "IE"})

        self.assertEqual(analysis["price_position"], "high")
        self.assertIn(analysis["verdict"], {"questionable", "risky"})
        self.assertGreater(int(analysis["estimated_market_max"]), int(analysis["estimated_price_max"]))
        self.assertNotIn("balanced", str(analysis["key_insight"]).lower())
        self.assertIn("price", str(analysis["key_insight"]).lower())
        self.assertNotIn("balanced", response.lower())
        self.assertIn("asking price is high", response.lower())

    async def test_run_structured_preview_pipeline_returns_text(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\nNCT 07-26\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
        }
        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="en", country="IE")

        self.assertTrue(isinstance(result, str) and result.strip())
        self.assertIn("🚗", result)

    async def test_same_car_different_language_changes_output_language(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\nNCT 07-26\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "IE",
        }

        async def fake_translate(text: str, target_lang: str):
            if target_lang == "fr":
                return "ANALYSE RAPIDE DE LA VOITURE"
            return text

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"), \
             patch("ai_core.pipeline.structured_pipeline.translate_from_english", side_effect=fake_translate):
            result_en = await run_structured_preview_pipeline(input_data=input_data, language="en", country="IE")
            result_fr = await run_structured_preview_pipeline(input_data=input_data, language="fr", country="IE")

        self.assertNotEqual(result_en, result_fr)
        self.assertIn("Verdict", result_en)
        self.assertIn("ANALYSE RAPIDE DE LA VOITURE", result_fr)

    async def test_ukrainian_hard_validation_regenerates_when_not_ukrainian(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "IE",
        }

        async def fake_analysis_stage(*args, **kwargs):
            return {
                "estimated_price_min": 2600,
                "estimated_price_max": 3600,
                "price_position": "low",
                "mileage_evaluation": "very_high",
                "risk_score": "high",
                "expected_cost_min": 1400,
                "expected_cost_max": 2600,
                "key_insight": "placeholder",
                "verdict": "risky",
                "currency": "EUR",
                "country": "IE",
            }

        calls = {"count": 0}

        async def fake_response_stage(analysis, data, context, currency, model="gpt-4o-mini"):
            calls["count"] += 1
            if calls["count"] == 1:
                return "This is English text"
            return (
                "🚗 Kia Rio (2011)\n"
                "📉 246,000 km | 💰 2100 EUR\n\n"
                "🚨 Вердикт: ризиково\n\n"
                "📊 Що по ринку:\n\n"
                "* діапазон: 2600-3600 EUR\n"
                "* позиція ціни: низька\n\n"
                "💸 Можливі витрати:\n"
                "1400-2600 EUR\n\n"
                "⚠️ Ризик:\n"
                "високий\n\n"
                "💣 Головне:\n"
                "Це український текст з літерою ї\n\n"
                "👉 Рішення:\n"
                "Купувати після перевірки"
            )

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="1"), \
             patch("ai_core.pipeline.structured_pipeline.run_openai_analysis_stage", side_effect=fake_analysis_stage), \
             patch("ai_core.pipeline.structured_pipeline.run_openai_response_stage", side_effect=fake_response_stage):
            result = await run_structured_preview_pipeline(input_data=input_data, language="uk", country="IE")

        self.assertGreaterEqual(calls["count"], 2)
        self.assertIn("ї", result)

    async def test_required_case_uk_ireland(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "Ірландія",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"), \
             patch("ai_core.pipeline.structured_pipeline.translate_from_english", return_value="Це український звіт з літерою ї"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="uk", country="Ірландія")

        self.assertIn("ї", result)

    async def test_required_case_pl_polska(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "Polska",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"), \
             patch("ai_core.pipeline.structured_pipeline.translate_from_english", return_value="To jest raport po polsku"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="pl", country="Polska")

        self.assertIn("polsku", result)

    async def test_translation_path_uk_input_ru_output(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "IE",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="ru", country="IE")

        self.assertIn("Вердикт", result)
        self.assertIn("Что по рынку", result)

    async def test_translation_path_ru_input_uk_output(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "IE",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="uk", country="IE")

        self.assertIn("Вердикт", result)
        self.assertIn("Що по ринку", result)

    async def test_mixed_input_becomes_clean_output(self):
        input_data = {
            "text": "Ціна good car 2100 EUR, пробіг 246000 km",
            "make": "Kia",
            "model": "Rio",
            "country": "IE",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"), \
             patch("ai_core.pipeline.structured_pipeline.translate_from_english", return_value="Це чистий український результат без english слів"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="uk", country="IE")

        self.assertTrue(validate_language(result, "uk"))

    async def test_ukrainian_preview_does_not_leak_english_key_insight(self):
        input_data = {
            "text": "Nissan Qashqai 2012\n274000 km\n2950 EUR\ndiesel",
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2012,
            "price": 2950,
            "currency": "EUR",
            "mileage_km": 274000,
            "fuel": "diesel",
            "country": "IE",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="uk", country="IE")

        self.assertIn("Головне", result)
        self.assertNotIn("Low price now", result)
        self.assertNotIn("costs later", result)
        self.assertTrue(validate_language(result, "uk"))

    async def test_english_input_no_translation(self):
        input_data = {
            "text": "Kia Rio 2011\n246000 km\n2100 EUR",
            "make": "Kia",
            "model": "Rio",
            "country": "IE",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="en", country="IE")

        self.assertIn("Verdict", result)

    async def test_required_case_de_de(self):
        input_data = {
            "text": "Volkswagen Golf 2014\n170000 km\n6500 EUR",
            "make": "Volkswagen",
            "model": "Golf",
            "country": "DE",
        }

        with patch("ai_core.pipeline.structured_pipeline.os.getenv", return_value="0"), \
             patch("ai_core.pipeline.structured_pipeline.translate_from_english", return_value="Das Risiko ist mittel"):
            result = await run_structured_preview_pipeline(input_data=input_data, language="de", country="DE")

        self.assertIn("mittel", result)


if __name__ == "__main__":
    unittest.main()
