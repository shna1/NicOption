import json
from pathlib import Path

from django.test import SimpleTestCase

from nicoption_dashboard.views import error_response


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ErrorResponseSecurityTests(SimpleTestCase):
    def test_internal_exception_detail_is_not_returned(self):
        response = error_response(
            RuntimeError("database password must never leave the server"),
            operation="دریافت اطلاعات",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            json.loads(response.content),
            {"error": "دریافت اطلاعات ناموفق بود"},
        )


class DeploymentSecurityConfigurationTests(SimpleTestCase):
    def test_proxy_sets_browser_security_headers(self):
        caddyfile = (PROJECT_ROOT / "deploy" / "Caddyfile").read_text()

        self.assertIn("Content-Security-Policy", caddyfile)
        self.assertIn("Permissions-Policy", caddyfile)
        self.assertIn("frame-ancestors 'none'", caddyfile)
        self.assertIn("img-src 'self' data:", caddyfile)
        self.assertIn("font-src 'self' data:", caddyfile)

    def test_production_hsts_is_one_year_without_subdomain_or_preload_expansion(self):
        production_env = (PROJECT_ROOT / ".env.production.example").read_text()

        self.assertIn("DJANGO_HSTS_SECONDS=31536000", production_env)
        self.assertIn("DJANGO_HSTS_INCLUDE_SUBDOMAINS=false", production_env)
        self.assertIn("DJANGO_HSTS_PRELOAD=false", production_env)

    def test_backup_script_restricts_directory_and_file_permissions(self):
        script = (PROJECT_ROOT / "deploy" / "backup-postgres.sh").read_text()

        self.assertIn('chmod 700 "$backup_dir"', script)
        self.assertIn("-exec chmod 600 {} +", script)
