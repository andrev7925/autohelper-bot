import unittest

from ai_core.context.ireland import get_ireland_market_context
from ai_core.pipeline.normalizer import normalize_vehicle_data


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


if __name__ == "__main__":
    unittest.main()