from django.urls import path

from . import views


app_name = "api-v1"

urlpatterns = [
    path("health", views.health, name="health"),
    path("auth/csrf", views.csrf, name="csrf"),
    path(
        "auth/signup-challenge",
        views.signup_challenge,
        name="signup-challenge",
    ),
    path(
        "auth/login",
        views.LoginView.as_view(),
        name="login",
    ),
    path(
        "auth/signup",
        views.SignupView.as_view(),
        name="signup",
    ),
    path(
        "auth/verification-status",
        views.verification_status,
        name="verification-status",
    ),
    path(
        "auth/verification-email",
        views.resend_verification_email,
        name="verification-email",
    ),
    path(
        "auth/logout",
        views.logout,
        name="logout",
    ),
    path(
        "auth/password",
        views.change_password,
        name="change-password",
    ),
    path("me", views.current_user, name="current-user"),
    path("preferences", views.preferences, name="preferences"),
    path("trade-imports", views.trade_import, name="trade-import"),
    path("history", views.history, name="history"),
    path(
        "order-book/catalog",
        views.order_book_catalog,
        name="order-book-catalog",
    ),
    path(
        "order-book",
        views.order_book,
        name="order-book",
    ),
    path(
        "covered-score",
        views.covered_score,
        name="covered-score",
    ),
]
