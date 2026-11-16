from django.core.management.base import BaseCommand

from nicoption_dashboard.models import DataSource, EconomicIndicator, IndicatorSource


CATALOG = (
    ("IR-INF", "تورم مصرف‌کننده", "Consumer Inflation", "macro", "monthly", "درصد"),
    ("IR_M2", "نقدینگی", "Money Supply (M2)", "macro", "monthly", "هزار میلیارد ریال"),
    ("IR_MONEY", "پول", "Money", "macro", "monthly", "هزار میلیارد ریال"),
    ("IR_MONETARY_BASE", "پایه پولی", "Monetary Base", "macro", "monthly", "هزار میلیارد ریال"),
    ("IR_CPI", "نرخ تورم مصرف‌کننده", "Consumer Price Inflation (CPI)", "macro", "monthly", "واحد"),
    ("IR_USD_FREE_MARKET", "قیمت ماهانه دلار بازار آزاد", "Monthly Free-Market USD/IRR", "fx", "monthly", "ریال"),
    ("IR_COIN_BAHAR_AZADI", "قیمت ماهانه سکه بهار آزادی", "Monthly Bahar Azadi Coin Price", "commodity", "monthly", "ریال"),
    ("IR_GOLD_18K", "قیمت ماهانه طلای ۱۸ عیار", "Monthly 18K Gold Price", "commodity", "monthly", "ریال"),
    ("IR_TETHER", "قیمت ماهانه تتر", "Monthly Tether Price", "fx", "monthly", "ریال"),
    ("IR_TEDPIX", "شاخص ماهانه کل بورس تهران", "Monthly Tehran Stock Exchange Total Index (TEDPIX)", "capital_market", "monthly", "واحد"),
)

PRICETODAY_CODES = {
    "IR_USD_FREE_MARKET",
    "IR_COIN_BAHAR_AZADI",
    "IR_GOLD_18K",
    "IR_TETHER",
}
FINPY_TSE_CODES = {"IR_TEDPIX"}


class Command(BaseCommand):
    help = "Create the economic-indicator metadata records without observations."

    def handle(self, *args, **options):
        created = 0
        unchanged = 0
        for code, name_fa, name_en, category, frequency, unit in CATALOG:
            indicator, was_created = EconomicIndicator.objects.get_or_create(
                code=code,
                defaults={
                    "name_fa": name_fa,
                    "name_en": name_en,
                    "kind": EconomicIndicator.Kind.ANALYTICAL if code in PRICETODAY_CODES else EconomicIndicator.Kind.OFFICIAL,
                    "category": category,
                    "frequency": frequency,
                    "unit": unit,
                },
            )
            if code in PRICETODAY_CODES and not was_created:
                indicator.name_fa = name_fa
                indicator.name_en = name_en
                indicator.kind = EconomicIndicator.Kind.ANALYTICAL
                indicator.category = category
                indicator.frequency = EconomicIndicator.Frequency.MONTHLY
                indicator.unit = unit
                indicator.save(update_fields=("name_fa", "name_en", "kind", "category", "frequency", "unit", "updated_at"))
            elif code in FINPY_TSE_CODES and not was_created:
                indicator.name_fa = name_fa
                indicator.name_en = name_en
                indicator.kind = EconomicIndicator.Kind.OFFICIAL
                indicator.category = category
                indicator.frequency = EconomicIndicator.Frequency.MONTHLY
                indicator.unit = unit
                indicator.save(update_fields=("name_fa", "name_en", "kind", "category", "frequency", "unit", "updated_at"))
            created += int(was_created)
            unchanged += int(not was_created)
        source, _ = DataSource.objects.get_or_create(
            name="PriceToDay",
            defaults={
                "organization": "PriceDB",
                "homepage_url": "https://priceto.day",
                "data_url": "https://api.priceto.day/v1/history/irr",
                "source_type": DataSource.SourceType.AGGREGATOR,
                "is_primary": True,
                "terms_notes": "داده تجمیعی بازار از PriceToDay؛ منبع بالادستی اعلام‌شده tgju.org است.",
            },
        )
        for indicator in EconomicIndicator.objects.filter(code__in=PRICETODAY_CODES):
            IndicatorSource.objects.filter(indicator=indicator, is_primary=True).exclude(source=source).update(is_primary=False)
            link, _ = IndicatorSource.objects.get_or_create(
                indicator=indicator,
                source=source,
                valid_from=None,
                defaults={"priority": 1, "is_primary": True},
            )
            if not link.is_primary or link.priority != 1:
                link.is_primary = True
                link.priority = 1
                link.save(update_fields=("is_primary", "priority"))
        finpy_source, _ = DataSource.objects.get_or_create(
            name="TSETMC via FinPy-TSE",
            defaults={
                "organization": "Tehran Securities Exchange Technology Management Co.",
                "homepage_url": "https://github.com/ARahimiQuant/finpy-tse",
                "data_url": "https://cdn.tsetmc.com/api/Index/GetIndexB2History/32097828799138957",
                "source_type": DataSource.SourceType.OFFICIAL,
                "is_primary": True,
                "terms_notes": "داده رسمی شاخص کل TSETMC که با کتابخانه FinPy-TSE دریافت می‌شود.",
            },
        )
        for indicator in EconomicIndicator.objects.filter(code__in=FINPY_TSE_CODES):
            IndicatorSource.objects.filter(indicator=indicator, is_primary=True).exclude(source=finpy_source).update(is_primary=False)
            link, _ = IndicatorSource.objects.get_or_create(
                indicator=indicator,
                source=finpy_source,
                valid_from=None,
                defaults={"priority": 1, "is_primary": True},
            )
            if not link.is_primary or link.priority != 1:
                link.is_primary = True
                link.priority = 1
                link.save(update_fields=("is_primary", "priority"))
        self.stdout.write(self.style.SUCCESS(f"created={created} unchanged={unchanged} observations=0"))
