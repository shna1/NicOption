import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from nicoption_dashboard.models import LoginAttempt


WINDOW = timedelta(minutes=10)
BLOCK_DURATION = timedelta(minutes=15)
LIMITS = {
    LoginAttempt.Scope.IDENTITY: 5,
    LoginAttempt.Scope.IP: 20,
}


def _digest(scope: str, value: str, *, purpose: str = "login") -> str:
    message = f"{purpose}-limit:{scope}:{value}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def login_keys(request, username: str) -> tuple[tuple[str, str], ...]:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    address = (forwarded.split(",", 1)[0] or request.META.get("REMOTE_ADDR", "")).strip()
    identity = username.strip().casefold()
    return (
        (LoginAttempt.Scope.IDENTITY, _digest(LoginAttempt.Scope.IDENTITY, identity)),
        (LoginAttempt.Scope.IP, _digest(LoginAttempt.Scope.IP, address or "unknown")),
    )


def signup_keys(request, username: str) -> tuple[tuple[str, str], ...]:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    address = (forwarded.split(",", 1)[0] or request.META.get("REMOTE_ADDR", "")).strip()
    identity = username.strip().casefold()
    return (
        (
            LoginAttempt.Scope.IDENTITY,
            _digest(LoginAttempt.Scope.IDENTITY, identity, purpose="signup"),
        ),
        (
            LoginAttempt.Scope.IP,
            _digest(LoginAttempt.Scope.IP, address or "unknown", purpose="signup"),
        ),
    )


def retry_after(keys: tuple[tuple[str, str], ...]) -> int:
    now = timezone.now()
    waits = [
        int((blocked_until - now).total_seconds()) + 1
        for blocked_until in LoginAttempt.objects.filter(
            key_hash__in=[key for _, key in keys], blocked_until__gt=now
        ).values_list("blocked_until", flat=True)
    ]
    return max(waits, default=0)


def record_failure(keys: tuple[tuple[str, str], ...]) -> int:
    now = timezone.now()
    with transaction.atomic():
        for scope, key_hash in keys:
            attempt, _ = LoginAttempt.objects.select_for_update().get_or_create(
                key_hash=key_hash,
                defaults={"scope": scope, "window_started": now},
            )
            if now - attempt.window_started >= WINDOW:
                attempt.failures = 0
                attempt.window_started = now
                attempt.blocked_until = None
            attempt.failures += 1
            if attempt.failures >= LIMITS[scope]:
                attempt.blocked_until = now + BLOCK_DURATION
            attempt.save()
    return retry_after(keys)


def clear_failures(keys: tuple[tuple[str, str], ...]) -> None:
    LoginAttempt.objects.filter(key_hash__in=[key for _, key in keys]).delete()
