import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from nicoption_dashboard.models import AccountPreference, LoginAttempt


class HealthApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_returns_versioned_drf_response(self):
        response = self.client.get(reverse("api-v1:health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "ok": True,
                "framework": "django-rest-framework",
                "api_version": "v1",
            },
        )
        self.assertEqual(response["Content-Type"], "application/json")


class CsrfApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_csrf_token_and_sets_cookie(self):
        response = self.client.get(
            reverse("api-v1:csrf"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertIn("csrf_token", response.data)
        self.assertTrue(response.data["csrf_token"])
        self.assertIn("csrftoken", response.cookies)


class LoginApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="workshop-user",
            password="test-password",
        )

    def test_rejects_login_without_csrf_token(self):
        response = self.client.post(
            reverse("api-v1:login"),
            {
                "username": "workshop-user",
                "password": "test-password",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_logs_in_with_valid_credentials_and_csrf_token(self):
        csrf_response = self.client.get(
            reverse("api-v1:csrf"),
        )
        csrf_token = csrf_response.data["csrf_token"]

        login_response = self.client.post(
            reverse("api-v1:login"),
            {
                "username": "workshop-user",
                "password": "test-password",
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(
            login_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            login_response.data,
            {
                "id": self.user.pk,
                "username": "workshop-user",
                "role": "viewer",
                "is_superuser": False,
                "home_path": "/dashboard",
            },
        )

        me_response = self.client.get(
            reverse("api-v1:current-user"),
        )

        self.assertEqual(
            me_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            me_response.data,
            {
                "id": self.user.pk,
                "username": "workshop-user",
                "role": "viewer",
                "is_superuser": False,
                "home_path": "/dashboard",
            },
        )

    def test_rejects_invalid_credentials_without_creating_session(self):
        csrf_response = self.client.get(
            reverse("api-v1:csrf"),
        )
        csrf_token = csrf_response.data["csrf_token"]

        response = self.client.post(
            reverse("api-v1:login"),
            {
                "username": "workshop-user",
                "password": "wrong-password",
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data,
            {
                "detail": "نام کاربری یا رمز عبور نادرست است.",
            },
        )
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_rate_limits_repeated_failed_logins(self):
        csrf_token = self.client.get(reverse("api-v1:csrf")).data["csrf_token"]

        for _ in range(4):
            response = self.client.post(
                reverse("api-v1:login"),
                {"username": "workshop-user", "password": "wrong-password"},
                format="json",
                HTTP_X_CSRFTOKEN=csrf_token,
                HTTP_X_FORWARDED_FOR="203.0.113.10",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            reverse("api-v1:login"),
            {"username": "workshop-user", "password": "wrong-password"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_X_FORWARDED_FOR="203.0.113.10",
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", response)
        self.assertGreater(LoginAttempt.objects.count(), 0)

    def test_successful_login_clears_failed_attempts(self):
        csrf_token = self.client.get(reverse("api-v1:csrf")).data["csrf_token"]
        request_options = {
            "format": "json",
            "HTTP_X_CSRFTOKEN": csrf_token,
            "HTTP_X_FORWARDED_FOR": "203.0.113.11",
        }
        self.client.post(
            reverse("api-v1:login"),
            {"username": "workshop-user", "password": "wrong-password"},
            **request_options,
        )
        self.assertGreater(LoginAttempt.objects.count(), 0)

        response = self.client.post(
            reverse("api-v1:login"),
            {"username": "workshop-user", "password": "test-password"},
            **request_options,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(LoginAttempt.objects.count(), 0)


class SignupApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_token(self):
        return self.client.get(reverse("api-v1:csrf")).data["csrf_token"]

    def challenge_answer(self):
        response = self.client.get(reverse("api-v1:signup-challenge"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = [int(value) for value in re.findall(r"\d+", response.data["question"])]
        self.assertEqual(len(values), 2)
        return str(sum(values))

    def signup_payload(self, **overrides):
        payload = {
            "username": "new-trader",
            "password1": "VioletHarbor!927",
            "password2": "VioletHarbor!927",
            "human_answer": self.challenge_answer(),
        }
        payload.update(overrides)
        return payload

    def test_rejects_signup_without_csrf_token(self):
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(get_user_model().objects.filter(username="new-trader").exists())

    def test_creates_pending_viewer_with_only_username_and_password(self):
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(username="new-trader")
        self.assertEqual(user.access_profile.role, "viewer")
        self.assertEqual(user.email, "")
        self.assertEqual(user.access_profile.phone_number, "")
        self.assertEqual(response.data["id"], user.pk)
        self.assertEqual(response.data["home_path"], "/verify-email")
        self.assertTrue(response.data["requires_email_verification"])
        self.assertIsNone(user.access_profile.email_verified_at)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_unverified_user_is_blocked_until_email_link_is_opened(self):
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(username="pending-user"),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        blocked_page = self.client.get("/dashboard")
        self.assertRedirects(
            blocked_page,
            "/verify-email?next=%2Fdashboard",
            fetch_redirect_response=False,
        )
        blocked_api = self.client.get(reverse("api-v1:current-user"))
        self.assertEqual(blocked_api.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked_api.json()["code"], "email_verification_required")

        send = self.client.post(
            reverse("api-v1:verification-email"),
            {"email": "pending@example.com"},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )
        self.assertEqual(send.status_code, status.HTTP_200_OK)

        link = re.search(r"https?://\S+/verify-email/confirm/\S+", mail.outbox[-1].body).group(0)
        confirm = self.client.get(link)
        self.assertRedirects(confirm, "/dashboard", fetch_redirect_response=False)
        user = get_user_model().objects.get(username="pending-user")
        self.assertIsNotNone(user.access_profile.email_verified_at)
        self.assertEqual(self.client.get("/dashboard").status_code, status.HTTP_200_OK)

    def test_rejects_duplicate_email_case_insensitively(self):
        get_user_model().objects.create_user(username="existing-email", email="trader@example.com")
        signup = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(username="duplicate-email-user"),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        response = self.client.post(
            reverse("api-v1:verification-email"),
            {"email": "Trader@Example.COM"},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["errors"])

    def test_resend_verification_email_is_rate_limited_then_sends(self):
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(username="resend-user"),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        token = self.csrf_token()
        sent = self.client.post(
            reverse("api-v1:verification-email"),
            {"email": "resend@example.com"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(sent.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

        limited = self.client.post(
            reverse("api-v1:verification-email"),
            {"email": "resend@example.com"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(limited.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", limited)

        user = get_user_model().objects.get(username="resend-user")
        user.access_profile.verification_email_sent_at = timezone.now() - timedelta(minutes=2)
        user.access_profile.save(update_fields=("verification_email_sent_at", "updated_at"))
        sent_again = self.client.post(
            reverse("api-v1:verification-email"),
            {"email": "resend@example.com"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(sent_again.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)

    def test_returns_field_errors_for_existing_username_and_weak_password(self):
        get_user_model().objects.create_user(username="existing-user")
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(
                username="existing-user",
                password1="12345678",
                password2="12345678",
            ),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data["errors"])
        self.assertIn("password2", response.data["errors"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rejects_mismatched_passwords_without_creating_user(self):
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(
                username="mismatch-user",
                password2="VioletHarbor!928",
            ),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password2", response.data["errors"])
        self.assertFalse(get_user_model().objects.filter(username="mismatch-user").exists())

    def test_rate_limits_repeated_invalid_signup_attempts(self):
        token = self.csrf_token()
        request_options = {
            "format": "json",
            "HTTP_X_CSRFTOKEN": token,
            "HTTP_X_FORWARDED_FOR": "203.0.113.44",
        }
        payload = {
            "username": "blocked-signup",
            "password1": "short",
            "password2": "different",
            "human_answer": self.challenge_answer(),
        }
        for _ in range(5):
            response = self.client.post(reverse("api-v1:signup"), payload, **request_options)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(reverse("api-v1:signup"), payload, **request_options)

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", response)

    def test_rejects_invalid_human_check_and_requires_a_new_challenge(self):
        response = self.client.post(
            reverse("api-v1:signup"),
            self.signup_payload(human_answer="999"),
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("human_answer", response.data["errors"])
        self.assertTrue(response.data["refresh_challenge"])
        self.assertNotIn("signup_human_challenge", self.client.session)



class LogoutApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="workshop-user",
            password="test-password",
        )
        logged_in = self.client.login(
            username="workshop-user",
            password="test-password",
        )
        self.assertTrue(logged_in)

    def test_logs_out_authenticated_session(self):
        csrf_response = self.client.get(
            reverse("api-v1:csrf"),
        )
        csrf_token = csrf_response.data["csrf_token"]

        logout_response = self.client.post(
            reverse("api-v1:logout"),
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(
            logout_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

        me_response = self.client.get(
            reverse("api-v1:current-user"),
        )

        self.assertEqual(
            me_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_rejects_logout_without_csrf_and_keeps_session(self):
        response = self.client.post(
            reverse("api-v1:logout"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(self.user.pk),
        )

        me_response = self.client.get(
            reverse("api-v1:current-user"),
        )

        self.assertEqual(
            me_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            me_response.data["id"],
            self.user.pk,
        )


class ChangePasswordApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="password-user",
            password="old-secure-password",
        )

    def csrf_token(self):
        return self.client.get(reverse("api-v1:csrf")).data["csrf_token"]

    def test_requires_authenticated_session(self):
        response = self.client.post(
            reverse("api-v1:change-password"),
            {
                "old_password": "old-secure-password",
                "new_password1": "new-secure-password",
                "new_password2": "new-secure-password",
            },
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rejects_request_without_csrf(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("api-v1:change-password"),
            {
                "old_password": "old-secure-password",
                "new_password1": "new-secure-password",
                "new_password2": "new-secure-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-secure-password"))

    def test_rejects_wrong_current_password(self):
        self.client.force_login(self.user)
        token = self.csrf_token()

        response = self.client.post(
            reverse("api-v1:change-password"),
            {
                "old_password": "wrong-password",
                "new_password1": "new-secure-password",
                "new_password2": "new-secure-password",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", response.data["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-secure-password"))

    def test_rejects_mismatched_new_passwords(self):
        self.client.force_login(self.user)
        token = self.csrf_token()

        response = self.client.post(
            reverse("api-v1:change-password"),
            {
                "old_password": "old-secure-password",
                "new_password1": "new-secure-password",
                "new_password2": "different-secure-password",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password2", response.data["errors"])

    def test_changes_password_and_keeps_current_session(self):
        self.client.force_login(self.user)
        token = self.csrf_token()

        response = self.client.post(
            reverse("api-v1:change-password"),
            {
                "old_password": "old-secure-password",
                "new_password1": "VioletHarbor!927",
                "new_password2": "VioletHarbor!927",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("old-secure-password"))
        self.assertTrue(self.user.check_password("VioletHarbor!927"))
        me_response = self.client.get(reverse("api-v1:current-user"))
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["id"], self.user.pk)


class CurrentUserApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="workshop-user",
            password="test-password",
        )

    def test_returns_authenticated_user_identity(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("api-v1:current-user"))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data,
            {
                "id": self.user.pk,
                "username": "workshop-user",
                "role": "viewer",
                "is_superuser": False,
                "home_path": "/dashboard",
            },
        )

    def test_identifies_global_admin(self):
        admin_user = get_user_model().objects.create_superuser(
            username="global-admin",
            password="test-password",
        )
        self.client.force_authenticate(user=admin_user)

        response = self.client.get(reverse("api-v1:current-user"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "admin")
        self.assertTrue(response.data["is_superuser"])

    def test_home_path_is_the_first_page_enabled_by_admin(self):
        AccountPreference.objects.create(
            owner=self.user,
            show_overview=False,
            show_articles=False,
            show_market=True,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("api-v1:current-user"))

        self.assertEqual(response.data["home_path"], "/opportunities")

    def test_requires_authentication(self):
        response = self.client.get(
            reverse("api-v1:current-user"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )


class LegacyPersonalApiSecurityTests(TestCase):
    @patch("nicoption_dashboard.views.get_runtime")
    def test_anonymous_user_cannot_read_market_data(self, get_runtime):
        response = self.client.get("/api/data")

        self.assertEqual(response.status_code, 403)
        get_runtime.assert_not_called()

    @patch("nicoption_dashboard.views.get_runtime")
    def test_anonymous_user_cannot_read_trades(self, get_runtime):
        response = self.client.get("/api/trades")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"error": "برای دسترسی به اطلاعات حساب وارد شوید"},
        )
        get_runtime.assert_not_called()

    @patch("nicoption_dashboard.views.get_runtime")
    def test_authenticated_user_can_reach_trades_service(self, get_runtime):
        user = get_user_model().objects.create_user(
            username="legacy-dashboard-user",
            password="test-password",
        )
        self.client.force_login(user)
        expected_payload = {"trades": [], "account": {}}
        get_runtime.return_value.trade_payload.return_value = expected_payload

        response = self.client.get("/api/trades")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_payload)
        get_runtime.assert_called_once_with(user.pk)
