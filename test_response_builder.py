import unittest

from ai_core.templates import get_response_builder


class ResponseBuilderLanguageTests(unittest.TestCase):
    def test_missing_key_returns_explicit_marker_without_english_fallback(self):
        builder = get_response_builder("ru")

        value = builder.text("preview.this_key_does_not_exist")

        self.assertEqual(value, "[MISSING_TRANSLATION:ru:preview.this_key_does_not_exist]")

    def test_ua_alias_resolves_to_uk(self):
        builder = get_response_builder("ua")

        language_name = builder.text("meta.language_name")

        self.assertEqual(language_name, "Ukrainian")


if __name__ == "__main__":
    unittest.main()
