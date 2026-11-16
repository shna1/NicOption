from pathlib import PurePosixPath
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .email_verification import is_email_verified


PUBLIC_PATHS = {
    "/",
    "/favicon.ico",
    "/health",
    "/ready",
    "/robots.txt",
    "/sitemap.xml",
    "/login",
    "/signup",
    "/verify-email",
    "/api/v1/auth/csrf",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/signup",
    "/api/v1/auth/signup-challenge",
    "/api/v1/auth/verification-status",
    "/api/v1/auth/verification-email",
}
PUBLIC_PREFIXES = ("/assets/", "/fonts/", "/verify-email/confirm/")
STATIC_SUFFIXES = {".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff2", ".ico"}


class VerifiedEmailRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if (
            path in PUBLIC_PATHS
            or path.startswith(PUBLIC_PREFIXES)
            or PurePosixPath(path).suffix.casefold() in STATIC_SUFFIXES
        ):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or is_email_verified(user):
            return self.get_response(request)

        if path.startswith("/api/"):
            return JsonResponse(
                {
                    "detail": "برای استفاده از امکانات، ابتدا ایمیل حساب را تأیید کنید.",
                    "code": "email_verification_required",
                    "verification_path": reverse("verify-email-page"),
                },
                status=403,
            )

        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{reverse('verify-email-page')}?{query}")
