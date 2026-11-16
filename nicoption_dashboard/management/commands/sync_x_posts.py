import os

from django.core.management.base import BaseCommand, CommandError

from nicoption_dashboard.x_content import (
    XContentConfigurationError,
    XContentUpstreamError,
    sync_x_account,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Fetch new posts from an X account, translate them to Persian, and create article drafts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.getenv("X_SOURCE_USERNAME", "financialjuice"),
            help="X username without @ (default: X_SOURCE_USERNAME or financialjuice)",
        )
        parser.add_argument(
            "--max-results",
            type=int,
            default=int(os.getenv("X_POST_MAX_RESULTS", "10")),
            help="Number of recent posts requested from X (5-100; default: 10)",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            default=_env_bool("X_POST_AUTO_PUBLISH", False),
            help="Publish translations that are not flagged for review; default creates drafts",
        )

    def handle(self, *args, **options):
        try:
            result = sync_x_account(
                username=options["username"],
                max_results=options["max_results"],
                auto_publish=options["publish"],
            )
        except (XContentConfigurationError, XContentUpstreamError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                " ".join(
                    (
                        f"fetched={result.fetched}",
                        f"discovered={result.discovered}",
                        f"translated={result.translated}",
                        f"published={result.published}",
                        f"failed={result.failed}",
                    )
                )
            )
        )
