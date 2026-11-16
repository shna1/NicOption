from .models import AccountPreference


FEATURE_FIELDS = {
    "overview": "show_overview",
    "articles": "show_articles",
    "option_market": "show_option_market",
    "economic_data": "show_economic_data",
    "market": "show_market",
    "tehran_options": "show_tehran_options",
    "order_flow": "show_order_flow",
    "commodity_exchange": "show_commodity_exchange",
    "trades": "show_trades",
    "closed_trades": "show_closed_trades",
    "profit_recognition": "show_profit_recognition",
    "calculator": "show_calculator",
    "settings": "show_settings",
    "forecast": "show_forecast",
}

OPTION_MARKET_FEATURES = frozenset({
    "market",
    "tehran_options",
    "order_flow",
    "commodity_exchange",
    "trades",
    "closed_trades",
    "profit_recognition",
    "forecast",
})

PAGE_FEATURES = {
    "/dashboard": "overview",
    "/index.html": "overview",
    "/articles": "articles",
    "/opportunities": "market",
    "/opportunities/covered-call": "market",
    "/opportunities/long-call": "market",
    "/market": "market",
    "/tehran-options": "tehran_options",
    "/commodity-exchange": "commodity_exchange",
    "/trades": "trades",
    "/trades/open": "trades",
    "/trades/closed": "closed_trades",
    "/trades/new": "trades",
    "/closed-trades": "closed_trades",
    "/profit-recognition": "profit_recognition",
    "/performance": "profit_recognition",
    "/performance/overview": "profit_recognition",
    "/performance/covered-call": "profit_recognition",
    "/performance/long-call": "profit_recognition",
    "/performance/realized-profit": "profit_recognition",
    "/calculator": "calculator",
    "/methodology": "calculator",
    "/settings": "settings",
    "/order-flow": "order_flow",
    "/forecast": "forecast",
    "/economic-indicators": "economic_data",
    "/economic-comparison": "economic_data",
    "/statistical-center": "economic_data",
    "/central-bank": "economic_data",
    "/monetary-details": "economic_data",
}


def get_user_preferences(user) -> AccountPreference:
    preference, _ = AccountPreference.objects.get_or_create(owner=user)
    return preference


def _preference_has_feature(preference: AccountPreference, feature: str) -> bool:
    if feature in OPTION_MARKET_FEATURES and not preference.show_option_market:
        return False
    return bool(getattr(preference, FEATURE_FIELDS[feature]))


def user_has_feature(user, feature: str) -> bool:
    if user.is_superuser:
        return True
    preference = get_user_preferences(user)
    return _preference_has_feature(preference, feature)


def user_feature_preferences(user) -> dict[str, bool]:
    """Return the effective permission map consumed by the client navigation."""
    if user.is_superuser:
        return {field: True for field in FEATURE_FIELDS.values()}
    preference = get_user_preferences(user)
    return {
        field: _preference_has_feature(preference, feature)
        for feature, field in FEATURE_FIELDS.items()
    }


def page_feature(path: str) -> str | None:
    """Resolve fixed pages and transaction detail URLs consistently."""
    normalized = "/" + str(path or "").strip("/")
    if normalized.startswith("/articles/"):
        return "articles"
    if normalized.startswith("/trades/") and normalized not in PAGE_FEATURES:
        return "trades"
    return PAGE_FEATURES.get(normalized)


def user_home_path(user) -> str:
    from .email_verification import is_email_verified

    if not is_email_verified(user):
        return "/verify-email"
    for path, feature in PAGE_FEATURES.items():
        if path == "/index.html":
            continue
        if user_has_feature(user, feature):
            return path
    return "/"
