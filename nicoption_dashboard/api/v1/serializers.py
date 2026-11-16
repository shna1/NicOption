from rest_framework import serializers


class HistoryQuerySerializer(serializers.Serializer):
    asset = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )
    source_asset = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )


class CurrentUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    role = serializers.SerializerMethodField()
    is_superuser = serializers.BooleanField(read_only=True)
    home_path = serializers.SerializerMethodField()

    def get_role(self, user):
        if user.is_superuser:
            return "admin"
        profile = getattr(user, "access_profile", None)
        return profile.role if profile else "viewer"

    def get_home_path(self, user):
        from nicoption_dashboard.feature_access import user_home_path

        return user_home_path(user)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )
    password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
    )


class UserPreferencesSerializer(serializers.Serializer):
    show_overview = serializers.BooleanField(required=False)
    show_articles = serializers.BooleanField(required=False)
    show_option_market = serializers.BooleanField(required=False)
    show_economic_data = serializers.BooleanField(required=False)
    show_market = serializers.BooleanField(required=False)
    show_tehran_options = serializers.BooleanField(required=False)
    show_order_flow = serializers.BooleanField(required=False)
    show_commodity_exchange = serializers.BooleanField(required=False)
    show_trades = serializers.BooleanField(required=False)
    show_closed_trades = serializers.BooleanField(required=False)
    show_profit_recognition = serializers.BooleanField(required=False)
    show_calculator = serializers.BooleanField(required=False)
    show_settings = serializers.BooleanField(required=False)
    show_forecast = serializers.BooleanField(required=False)


class TradeImportSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    status = serializers.ChoiceField(choices=("open", "closed"))
    confirm = serializers.BooleanField(required=False, default=False)


class OrderBookQuerySerializer(serializers.Serializer):
    market = serializers.ChoiceField(
        choices=("tehran", "goods"),
        required=False,
        default="tehran",
    )
    instrument_type = serializers.ChoiceField(
        choices=("option", "base"),
        required=False,
        default="option",
    )
    symbol = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )
    refresh = serializers.BooleanField(
        required=False,
        default=False,
    )


class OptionalFloatField(serializers.FloatField):
    def to_internal_value(self, data):
        if isinstance(data, str) and not data.strip():
            return None
        return super().to_internal_value(data)


class CoveredScoreRequestSerializer(serializers.Serializer):
    market = serializers.ChoiceField(
        choices=("tehran", "goods"),
        required=False,
        default="tehran",
    )
    asset = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )
    symbol = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )
    base_price = serializers.FloatField(required=True)
    premium = serializers.FloatField(required=True)
    strike = serializers.FloatField(required=True)
    days = serializers.FloatField(required=True)
    transaction_value = OptionalFloatField(
        required=False,
        allow_null=True,
        default=None,
    )
    option_last = OptionalFloatField(
        required=False,
        allow_null=True,
        default=None,
    )
