from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.html import conditional_escape
from django.utils.http import urlsafe_base64_encode


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "nicoption_dashboard.email_verification"

    def _make_hash_value(self, user, timestamp):
        from .models import UserAccessProfile

        verified = UserAccessProfile.objects.filter(user_id=user.pk).values_list(
            "email_verified_at", flat=True
        ).first()
        return f"{user.pk}{timestamp}{user.email.casefold()}{verified or ''}"


email_verification_token = EmailVerificationTokenGenerator()


def is_email_verified(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    from .models import UserAccessProfile

    return UserAccessProfile.objects.filter(
        user_id=user.pk,
        email_verified_at__isnull=False,
    ).exists()


def verification_url(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    path = reverse("verify-email-confirm", kwargs={"uidb64": uid, "token": token})
    return urljoin(f"{settings.PUBLIC_SITE_ORIGIN}/", path.lstrip("/"))


def send_verification_email(user) -> None:
    link = verification_url(user)
    safe_username = conditional_escape(user.username)
    subject = "تأیید ایمیل حساب nicoption"
    text = (
        f"سلام {user.username}،\n\n"
        "برای فعال‌شدن امکانات حساب nicoption، ایمیل خود را از لینک زیر تأیید کنید:\n"
        f"{link}\n\n"
        "این لینک ۲۴ ساعت اعتبار دارد. اگر این حساب را شما نساخته‌اید، این پیام را نادیده بگیرید."
    )
    html = (
        '<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;line-height:1.9">'
        f"<p>سلام {safe_username}،</p>"
        "<p>برای فعال‌شدن امکانات حساب nicoption، ایمیل خود را تأیید کنید.</p>"
        f'<p><a href="{link}">تأیید ایمیل و فعال‌سازی حساب</a></p>'
        "<p>این لینک ۲۴ ساعت اعتبار دارد. اگر این حساب را شما نساخته‌اید، این پیام را نادیده بگیرید.</p>"
        "</div>"
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)
    profile = user.access_profile
    profile.verification_email_sent_at = timezone.now()
    profile.save(update_fields=("verification_email_sent_at", "updated_at"))
