import logging
import secrets
import smtplib
from datetime import timedelta

from django.contrib.auth import (
    authenticate,
    login as django_login,
    logout as django_logout,
    update_session_auth_hash,
)
from django.contrib.auth.forms import PasswordChangeForm
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.core.mail import BadHeaderError
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from bambo_bot.web import calculate_custom_covered_call
from nicoption_dashboard.services import get_runtime
from nicoption_dashboard.email_verification import is_email_verified, send_verification_email
from nicoption_dashboard.auth_forms import DIGIT_TRANSLATION, SignupForm, VerificationEmailForm
from nicoption_dashboard.login_security import (
    clear_failures,
    login_keys,
    record_failure,
    retry_after,
    signup_keys,
)
from nicoption_dashboard.feature_access import (
    FEATURE_FIELDS,
    user_feature_preferences,
    user_has_feature,
)
from nicoption_dashboard.trade_imports import import_trade_records, parse_trade_csv

from .exceptions import (
    CoveredScoreServiceError,
    HistoryProviderError,
    OrderBookCatalogProviderError,
    OrderBookNotFound,
    OrderBookProviderError,
)
from .serializers import (
    CoveredScoreRequestSerializer,
    CurrentUserSerializer,
    HistoryQuerySerializer,
    LoginSerializer,
    OrderBookQuerySerializer,
    TradeImportSerializer,
)


LOGGER = logging.getLogger(__name__)
SIGNUP_CHALLENGE_SESSION_KEY = "signup_human_challenge"
SIGNUP_CHALLENGE_MAX_AGE_SECONDS = 600


def _new_signup_challenge(request) -> str:
    left = secrets.randbelow(8) + 2
    right = secrets.randbelow(8) + 2
    request.session[SIGNUP_CHALLENGE_SESSION_KEY] = {
        "answer": left + right,
        "issued_at": int(timezone.now().timestamp()),
    }
    return f"حاصل {left} + {right} چند است؟"


def _human_answer_is_valid(request, raw_answer) -> bool:
    challenge = request.session.get(SIGNUP_CHALLENGE_SESSION_KEY)
    if not isinstance(challenge, dict):
        return False
    try:
        age = int(timezone.now().timestamp()) - int(challenge["issued_at"])
        answer = int(str(raw_answer or "").strip().translate(DIGIT_TRANSLATION))
        expected = int(challenge["answer"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= age <= SIGNUP_CHALLENGE_MAX_AGE_SECONDS and answer == expected


def require_feature(request: Request, feature: str) -> None:
    if not user_has_feature(request.user, feature):
        raise PermissionDenied("این بخش در تنظیمات حساب شما غیرفعال است.")


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    return Response(
        {
            "ok": True,
            "framework": "django-rest-framework",
            "api_version": "v1",
        }
    )


@api_view(["GET"])
def history(request: Request) -> Response:
    serializer = HistoryQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)

    query = serializer.validated_data
    try:
        payload = get_runtime().history.fetch(
            query["asset"],
            query["source_asset"],
        )
    except Exception as exc:
        LOGGER.exception("History provider request failed")
        raise HistoryProviderError() from exc

    return Response(payload)


@api_view(["GET"])
def order_book_catalog(request: Request) -> Response:
    require_feature(request, "order_flow")
    try:
        payload = get_runtime().cache.order_flow_catalog()
    except Exception as exc:
        LOGGER.exception("Order-book catalog request failed")
        raise OrderBookCatalogProviderError() from exc

    return Response(payload)


@api_view(["GET"])
def order_book(request: Request) -> Response:
    require_feature(request, "order_flow")
    serializer = OrderBookQuerySerializer(
        data=request.query_params,
    )
    serializer.is_valid(raise_exception=True)

    query = serializer.validated_data

    try:
        payload = get_runtime().cache.order_flow(
            market=query["market"],
            instrument_type=query["instrument_type"],
            symbol=query["symbol"],
            force=query["refresh"],
        )
    except KeyError as exc:
        raise OrderBookNotFound() from exc
    except Exception as exc:
        LOGGER.exception("Order-book provider request failed")
        raise OrderBookProviderError() from exc

    return Response(payload)


@api_view(["POST"])
def covered_score(request: Request) -> Response:
    serializer = CoveredScoreRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    payload = dict(serializer.validated_data)
    try:
        runtime = get_runtime()
        dashboard = runtime.cache.get()
        liquidity_values = [
            item["transaction_value"]
            for group in dashboard["covered_call"]
            if group["market"] == payload["market"]
            for item in group["items"]
        ]
    except Exception as exc:
        LOGGER.exception("Covered-score market data failed")
        raise CoveredScoreServiceError() from exc

    try:
        result = calculate_custom_covered_call(
            payload,
            liquidity_values,
            runtime.settings.long_underlying_interest_rate,
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        LOGGER.exception("Covered-score calculation crashed")
        raise CoveredScoreServiceError() from exc

    return Response(result)


@api_view(["GET"])
def current_user(request: Request) -> Response:
    serializer = CurrentUserSerializer(request.user)
    return Response(serializer.data)


@api_view(["GET"])
def preferences(request: Request) -> Response:
    if request.user.is_superuser:
        return Response({field: True for field in FEATURE_FIELDS.values()})
    return Response(user_feature_preferences(request.user))


@api_view(["POST"])
def trade_import(request: Request) -> Response:
    serializer = TradeImportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        parsed = parse_trade_csv(
            values["file"], owner_id=request.user.pk, status=values["status"]
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
        )

    preview = {
        "status": values["status"],
        "total": len(parsed.records) + len(parsed.errors),
        "valid": len(parsed.records),
        "invalid": len(parsed.errors),
        "valid_trades": sum(
            item["_record_type"] == "trade" for item in parsed.records
        ),
        "valid_underlyings": sum(
            item["_record_type"] == "underlying" for item in parsed.records
        ),
        "errors": parsed.errors[:50],
        "items": [
            {
                "row": index,
                "record_type": item["_record_type"],
                "strategy_type": item.get("strategy_type"),
                "market": item["market"],
                "asset": item["asset"],
                "option_symbol": item.get("option_symbol"),
                "entry_date": item["entry_date"],
                "status": item["status"],
            }
            for index, item in enumerate(parsed.records, start=2)
        ][:50],
    }
    if not values["confirm"]:
        return Response({"mode": "preview", **preview})
    if parsed.errors:
        return Response(
            {
                "detail": "ابتدا خطاهای فایل را اصلاح کنید؛ هیچ معامله‌ای ثبت نشد.",
                **preview,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    result = import_trade_records(parsed, owner_id=request.user.pk)
    return Response({"mode": "import", **preview, **result}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request: Request) -> Response:
    return Response(
        {
            "csrf_token": get_token(request),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def signup_challenge(request: Request) -> Response:
    response = Response({"question": _new_signup_challenge(request._request)})
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET"])
def verification_status(request: Request) -> Response:
    return Response(
        {
            "email": request.user.email,
            "email_verified": is_email_verified(request.user),
            "home_path": CurrentUserSerializer(request.user).data["home_path"],
        }
    )


@api_view(["POST"])
def resend_verification_email(request: Request) -> Response:
    if is_email_verified(request.user):
        return Response(
            {"detail": "ایمیل این حساب قبلاً تأیید شده است.", "email_verified": True}
        )
    profile = request.user.access_profile
    now = timezone.now()
    if profile.verification_email_sent_at:
        available_at = profile.verification_email_sent_at + timedelta(seconds=60)
        if available_at > now:
            wait = int((available_at - now).total_seconds()) + 1
            response = Response(
                {"detail": "برای ارسال دوباره کمی صبر کنید.", "retry_after": wait},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(wait)
            return response
    form = VerificationEmailForm(data={"email": request.data.get("email") or ""}, user=request.user)
    if not form.is_valid():
        errors = {
            field: [item["message"] for item in messages]
            for field, messages in form.errors.get_json_data().items()
        }
        return Response(
            {"detail": "ایمیل معتبر را وارد کنید.", "errors": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    request.user.email = form.cleaned_data["email"]
    request.user.save(update_fields=("email",))
    try:
        send_verification_email(request.user)
    except (BadHeaderError, OSError, ConnectionError, smtplib.SMTPException):
        LOGGER.exception("Verification email delivery failed for user %s", request.user.pk)
        return Response(
            {"detail": "ارسال ایمیل انجام نشد. کمی بعد دوباره تلاش کنید."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"detail": "لینک تأیید ارسال شد."})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        credentials = serializer.validated_data
        keys = login_keys(request._request, credentials["username"])
        wait = retry_after(keys)
        if wait:
            response = Response(
                {"detail": "تلاش‌های ورود بیش از حد مجاز است. کمی بعد دوباره امتحان کنید."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(wait)
            return response

        user = authenticate(
            request=request._request,
            username=credentials["username"],
            password=credentials["password"],
        )

        if user is None:
            wait = record_failure(keys)
            if wait:
                response = Response(
                    {"detail": "تلاش‌های ورود بیش از حد مجاز است. کمی بعد دوباره امتحان کنید."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
                response["Retry-After"] = str(wait)
                return response
            return Response(
                {
                    "detail": "نام کاربری یا رمز عبور نادرست است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        clear_failures(keys)
        django_login(request._request, user)

        return Response(
            CurrentUserSerializer(user).data,
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class SignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        username = str(request.data.get("username") or "").strip()
        keys = signup_keys(request._request, username)
        wait = retry_after(keys)
        if wait:
            response = Response(
                {"detail": "تلاش‌های ثبت‌نام بیش از حد مجاز است. کمی بعد دوباره امتحان کنید."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(wait)
            return response

        if not _human_answer_is_valid(request._request, request.data.get("human_answer")):
            request.session.pop(SIGNUP_CHALLENGE_SESSION_KEY, None)
            record_failure(keys)
            return Response(
                {
                    "detail": "لطفاً خطاهای فرم را اصلاح کنید.",
                    "errors": {"human_answer": ["پاسخ بررسی انسانی درست نیست یا زمان آن گذشته است."]},
                    "refresh_challenge": True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = SignupForm(
            data={
                "username": username,
                "password1": request.data.get("password1") or "",
                "password2": request.data.get("password2") or "",
            }
        )
        if not form.is_valid():
            record_failure(keys)
            errors = {
                field: [item["message"] for item in messages]
                for field, messages in form.errors.get_json_data().items()
            }
            return Response(
                {"detail": "لطفاً خطاهای فرم را اصلاح کنید.", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            record_failure(keys)
            return Response(
                {
                    "detail": "لطفاً خطاهای فرم را اصلاح کنید.",
                    "errors": {"username": ["این نام کاربری قبلاً ثبت شده است."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        record_failure(keys)
        request.session.pop(SIGNUP_CHALLENGE_SESSION_KEY, None)
        django_login(request._request, user)
        payload = CurrentUserSerializer(user).data
        payload["requires_email_verification"] = True
        return Response(
            payload,
            status=status.HTTP_201_CREATED,
        )


@api_view(["POST"])
def logout(request: Request) -> Response:
    django_logout(request._request)
    return Response(
        status=status.HTTP_204_NO_CONTENT,
    )


@api_view(["POST"])
def change_password(request: Request) -> Response:
    form = PasswordChangeForm(user=request.user, data=request.data)
    if not form.is_valid():
        errors = {
            field: [item["message"] for item in messages]
            for field, messages in form.errors.get_json_data().items()
        }
        return Response(
            {
                "detail": "لطفاً خطاهای فرم را اصلاح کنید.",
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = form.save()
    update_session_auth_hash(request._request, user)
    return Response(
        {"detail": "رمز عبور با موفقیت تغییر کرد."},
        status=status.HTTP_200_OK,
    )
