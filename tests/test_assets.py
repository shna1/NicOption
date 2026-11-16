import unittest

from bambo_bot.assets import canonical_asset, canonical_tehran_asset


class AssetMappingTests(unittest.TestCase):
    def test_arabic_kaf_in_kahroba_is_normalized(self):
        self.assertEqual(canonical_asset("كهربا", "KASH05C10"), "کهربا")

    def test_javaher_is_dena_zagros(self):
        self.assertEqual(canonical_asset("جواهر", "JZMO05C10"), "صندوق طلای دنا زاگرس")

    def test_cu_symbol_repairs_generic_base_label(self):
        self.assertEqual(canonical_asset("دارایی پایه", "CUMO05C180"), "مس کاتد")

    def test_silver_fund_is_canonicalized(self):
        self.assertEqual(
            canonical_asset("صندوق نقره کهکشان فیروزه", "NQAB05C1200"),
            "صندوق نقره کهکشان فیروزه",
        )

    def test_deraz_options_are_mapped_to_hamtaraz(self):
        self.assertEqual(
            canonical_tehran_asset("هم_وزن", "ضراز8007"),
            "هم‌تراز",
        )

    def test_other_tehran_options_keep_their_reported_underlying(self):
        self.assertEqual(
            canonical_tehran_asset("وبملت", "ضملت6019"),
            "وبملت",
        )


if __name__ == "__main__":
    unittest.main()
