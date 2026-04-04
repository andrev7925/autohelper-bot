import unittest

from ai_core.templates.validator import check_all_languages_have_same_keys


class I18nValidatorTests(unittest.TestCase):
    def test_all_locale_files_have_consistent_keys(self):
        check_all_languages_have_same_keys()


if __name__ == "__main__":
    unittest.main()
