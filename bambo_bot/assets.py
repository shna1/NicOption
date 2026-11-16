from __future__ import annotations

import re
import unicodedata


TARGET_ASSETS = (
    "صندوق طلای لوتوس",
    "کهربا",
    "طلای 24 عیار",
    "صندوق طلای دنا زاگرس",
    "شمش نقره",
    "صندوق نقره کهکشان فیروزه",
    "مس کاتد",
    "صندوق طلای درخشان",
    "صندوق طلای کارآمد",
)


def normalize_fa(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"}))
    return re.sub(r"\s+", " ", value).strip()


def canonical_asset(source_asset: str, option_symbol: str) -> str | None:
    name = normalize_fa(source_asset)
    symbol = (option_symbol or "").upper()

    if symbol.startswith("CU") or name == "مس کاتد":
        return "مس کاتد"
    aliases = {
        "صندوق طلای لوتوس": "صندوق طلای لوتوس",
        "کهربا": "کهربا",
        "طلای 24 عیار": "طلای 24 عیار",
        "طلای ۲۴ عیار": "طلای 24 عیار",
        "شمش طلا": "طلای 24 عیار",
        "شمش طلای 24 عیار": "طلای 24 عیار",
        "شمش طلای ۲۴ عیار": "طلای 24 عیار",
        "جواهر": "صندوق طلای دنا زاگرس",
        "صندوق طلای دنا زاگرس": "صندوق طلای دنا زاگرس",
        "شمش نقره": "شمش نقره",
        "صندوق نقره کهکشان فیروزه": "صندوق نقره کهکشان فیروزه",
        "صندوق س.کالای کهکشان فیروزه1": "صندوق نقره کهکشان فیروزه",
        "صندوق س. کالای کهکشان فیروزه1": "صندوق نقره کهکشان فیروزه",
        "نقرابی": "صندوق نقره کهکشان فیروزه",
        "درخشان": "صندوق طلای درخشان",
        "صندوق طلای درخشان": "صندوق طلای درخشان",
        "صندوق طلای کارآمد": "صندوق طلای کارآمد",
    }
    return aliases.get(name)


def canonical_tehran_asset(source_asset: str, option_symbol: str) -> str | None:
    """Repair known Tehran-option underlying labels returned by Bambo."""
    name = normalize_fa(source_asset)
    symbol = normalize_fa(option_symbol)

    # Bambo currently reports the underlying of the «ضراز» option family as
    # «هم_وزن», while these contracts belong to the Ham-Taraz ETF.
    if symbol.startswith("ضراز"):
        return "هم‌تراز"
    return name or None
