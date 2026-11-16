import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from nicoption_dashboard.models import Article, ArticleImage


class ArticleEditorAdminTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.admin_user = get_user_model().objects.create_superuser(
            username="article-admin",
            password="test-password",
        )
        self.client.force_login(self.admin_user)

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_article_add_page_uses_rich_editor(self):
        response = self.client.get(reverse("admin:nicoption_dashboard_article_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-article-editor')
        self.assertContains(response, "درج تصویر")
        self.assertContains(response, "/admin/article-editor.js")

    def test_image_upload_returns_private_article_media_url(self):
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"article-image"
        upload = SimpleUploadedFile(
            "chart.png",
            image_bytes,
            content_type="image/png",
        )
        response = self.client.post(
            reverse("admin:nicoption_dashboard_article_image_upload"),
            {"image": upload, "alt_text": "نمودار بازده اختیار معامله"},
        )

        self.assertEqual(response.status_code, 201)
        image = ArticleImage.objects.get()
        self.assertEqual(response.json()["url"], reverse("article-media", kwargs={"image_id": image.pk}))
        media_response = self.client.get(response.json()["url"])
        self.assertEqual(media_response.status_code, 200)
        self.assertEqual(media_response["Content-Type"], "image/png")
        self.assertEqual(b"".join(media_response.streaming_content), image_bytes)

    def test_image_upload_rejects_active_svg_content(self):
        response = self.client.post(
            reverse("admin:nicoption_dashboard_article_image_upload"),
            {
                "image": SimpleUploadedFile(
                    "unsafe.svg",
                    b'<svg onload="alert(1)"></svg>',
                    content_type="image/svg+xml",
                ),
                "alt_text": "تصویر نامعتبر",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ArticleImage.objects.count(), 0)


class ArticleContentSafetyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="article-reader")
        self.client.force_login(self.user)

    def test_article_html_is_sanitized_before_api_rendering(self):
        article = Article.objects.create(
            title="تحلیل بازار",
            slug="market-analysis",
            summary="خلاصه",
            body=(
                '<h2 onclick="alert(1)">عنوان امن</h2>'
                '<script>alert(1)</script>'
                '<a href="javascript:alert(1)">پیوند ناسالم</a>'
            ),
            is_published=True,
            published_at=timezone.now(),
        )

        article.refresh_from_db()
        self.assertNotIn("onclick", article.body)
        self.assertNotIn("<script", article.body)
        self.assertNotIn("javascript:", article.body)

        response = self.client.get(reverse("api-articles"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["articles"][0]["body"], article.body)
