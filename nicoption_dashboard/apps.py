from django.apps import AppConfig


class NicoptionDashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nicoption_dashboard"

    def ready(self):
        from . import signals  # noqa: F401
    verbose_name = "NI Option"
