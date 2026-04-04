import unittest

from ai_core.context.ireland import get_ireland_market_context
from ai_core.pipeline.normalizer import normalize_vehicle_data
from handlers.buttons.analyze_ad import _merge_site_data


class PriceNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.ireland = get_ireland_market_context()

    def test_price_line_after_tax_is_preserved(self):
        sample = {
            "title": "Mercedes B180",
            "brand_model": "Mercedes B180",
            "text": (
                "Mercedes B180\n"
                "Automatic\n"
                "Low mileage 120.000 kms\n"
                "NCT-5-26\n"
                "Tax -4/26\n"
                "Price 9.250💶\n"
                "Dublin"
            ),
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("price"), 9250.0)
        self.assertEqual(normalized.get("currency"), "EUR")

    def test_market_currency_used_when_price_has_no_explicit_currency(self):
        sample = {
            "title": "Volkswagen Golf",
            "brand_model": "Volkswagen Golf",
            "text": "Volkswagen Golf\nPrice 8400\nDublin",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("price"), 8400.0)
        self.assertEqual(normalized.get("currency"), "EUR")

    def test_tax_line_alone_is_not_treated_as_car_price(self):
        sample = {
            "title": "Toyota Yaris",
            "brand_model": "Toyota Yaris",
            "text": "Toyota Yaris\nRoad tax 280 EUR\nNCT 06/26\nDublin",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIsNone(normalized.get("price"))
        self.assertEqual(normalized.get("currency"), "EUR")

    def test_model_number_is_not_concatenated_with_next_line_price(self):
        sample = {
            "title": "Peugeot 3008",
            "brand_model": "Peugeot 3008",
            "text": "Peugeot 3008\n950€\nNo tax no nct\nWaterford",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("price"), 950.0)
        self.assertEqual(normalized.get("currency"), "EUR")

    def test_ukrainian_attached_km_text_overrides_truncated_ocr(self):
        sample = {
            "make": "Mazda",
            "model": "CX-5",
            "year": 2017,
            "mileage": 20323,
            "mileage_km": 20323,
            "mileage_unit": "km",
            "text": "Mazda CX5 2017\nПробіг 203.800км\n12 500€",
            "price": "12500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage_km"), 203800)
        self.assertEqual(normalized.get("mileage"), 203800)

    def test_russian_thousand_miles_text_is_supported(self):
        sample = {
            "text": "Пробег 171 тыс. миль\nЦена 10800",
            "price": "10800",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIn(171000, normalized.get("text_mileage_candidates") or [])

    def test_french_kilometrage_is_supported(self):
        sample = {
            "text": "Kilométrage 203 800 km\nPrix 12500",
            "price": "12500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIn(203800, normalized.get("text_mileage_candidates") or [])

    def test_german_laufleistung_is_supported(self):
        sample = {
            "text": "Laufleistung 203.800 km\nPreis 12500",
            "price": "12500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIn(203800, normalized.get("text_mileage_candidates") or [])

    def test_service_km_is_ignored_and_short_mileage_is_corrected(self):
        sample = {
            "year": 2014,
            "text": "Timing belt replaced 2000 km ago\nMileage 292 km\nPrice 4500€",
            "price": "4500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage_km"), 292000)
        self.assertEqual(normalized.get("mileage"), 292000)
        self.assertEqual(normalized.get("mileage_confidence"), "low")
        self.assertEqual(normalized.get("mileage_note"), "interpreted as thousands (likely shorthand)")

    def test_recent_car_short_mileage_is_not_auto_corrected(self):
        sample = {
            "year": 2025,
            "text": "Mileage 292 km\nPrice 31000€",
            "price": "31000",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage_km"), 292)
        self.assertEqual(normalized.get("mileage"), 292)

    def test_spanish_kilometraje_is_supported(self):
        sample = {
            "text": "Kilometraje 203.800 km\nPrecio 12500",
            "price": "12500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIn(203800, normalized.get("text_mileage_candidates") or [])

    def test_portuguese_quilometragem_is_supported(self):
        sample = {
            "text": "Quilometragem 203.800 km\nPreço 12500",
            "price": "12500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIn(203800, normalized.get("text_mileage_candidates") or [])

    def test_turkish_km_text_is_supported(self):
        sample = {
            "text": "203.800 km\nFiyat 12500",
            "price": "12500",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertIn(203800, normalized.get("text_mileage_candidates") or [])

    def test_merge_prefers_text_miles_over_photo_unit_guess(self):
        photo_data = {
            "mileage": 230072,
            "mileage_km": 230072,
            "mileage_unit": "km",
            "source": "preview_batch",
        }
        text_data = {
            "text": "Пробег: 230,000 миль",
            "mileage": "230000",
            "mileage_miles": "230000",
            "mileage_km": "370148",
            "mileage_unit": "miles",
        }

        merged = _merge_site_data(photo_data, text_data)

        self.assertEqual(merged.get("mileage_unit"), "miles")
        self.assertEqual(int(merged.get("mileage")), 230000)
        self.assertEqual(int(merged.get("mileage_miles")), 230000)
        self.assertEqual(int(merged.get("mileage_km")), 370148)

    def test_explicit_text_miles_override_blurry_photo_km_guess(self):
        sample = {
            "make": "Nissan",
            "model": "Qashqai",
            "year": 2010,
            "mileage": 230000,
            "mileage_km": 230072,
            "mileage_miles": "230000",
            "mileage_unit": "miles",
            "text": "Пробег: 230,000 миль (в основном трасса)",
            "price": "2900",
            "currency": "EUR",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage"), 230000)
        self.assertEqual(normalized.get("mileage_km"), 370148)
        self.assertEqual(normalized.get("mileage_conflict"), False)
        self.assertEqual(normalized.get("mileage_confidence"), "high")

    def test_noisy_title_keeps_clean_model_name(self):
        sample = {
            "make": "Nissan",
            "model": "",
            "title": "Nissan Qashqai +2 • 7 мест • 1.5 дизель • Панорама • Камера",
            "text": "Цена 2900€\nПробег: 230,000 миль",
            "price": "2900",
            "currency": "EUR",
            "mileage": "230000",
            "mileage_miles": "230000",
            "mileage_km": "370148",
            "mileage_unit": "miles",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("make"), "Nissan")
        self.assertEqual(normalized.get("model"), "Qashqai +2")

    def test_mileage_priority_listing_text_over_odometer_and_document(self):
        sample = {
            "mileage": "180000",
            "mileage_km": "180000",
            "mileage_unit": "km",
            "dashboard_mileage": "200000",
            "text": "Пробег: 230,000 миль",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage_source"), "listing_text")
        self.assertEqual(normalized.get("mileage_unit"), "miles")
        self.assertEqual(normalized.get("mileage"), 230000)
        self.assertEqual(normalized.get("mileage_km"), 370148)

    def test_mileage_priority_odometer_over_document_when_no_text(self):
        sample = {
            "mileage": "180000",
            "mileage_km": "180000",
            "mileage_unit": "km",
            "dashboard_mileage": "205500",
            "text": "NCT till 2026",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage_source"), "odometer")
        self.assertEqual(normalized.get("mileage_unit"), "km")
        self.assertEqual(normalized.get("mileage"), 205500)
        self.assertEqual(normalized.get("mileage_km"), 205500)

    def test_mileage_priority_document_when_text_and_odometer_missing(self):
        sample = {
            "mileage": "230000",
            "mileage_miles": "230000",
            "mileage_unit": "miles",
            "text": "good condition",
        }

        normalized = normalize_vehicle_data(sample, self.ireland)

        self.assertEqual(normalized.get("mileage_source"), "document")
        self.assertEqual(normalized.get("mileage_unit"), "miles")
        self.assertEqual(normalized.get("mileage"), 230000)
        self.assertEqual(normalized.get("mileage_km"), 370148)


if __name__ == "__main__":
    unittest.main()