import json
from datetime import datetime, timezone as dt_timezone
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from nicoption_dashboard.models import Article, XPostTranslation
from nicoption_dashboard.x_content import XContentConfigurationError, sync_x_account


def json_response(payload, status_code=200):
    response = Mock()
    response.ok = 200 <= status_code < 300
    response.status_code = status_code
    response.headers = {}
    response.json.return_value = payload
    return response


class XContentSyncTests(TestCase):
    env = {
        "X_BEARER_TOKEN": "x-test-token",
        "OPENAI_API_KEY": "openai-test-token",
        "OPENAI_TRANSLATION_MODEL": "gpt-4o-mini",
    }

    def upstream_responses(self, *, needs_review=False):
        translation = {
            "title": "فدرال رزرو نرخ بهره را ثابت نگه داشت",
            "summary": "فدرال رزرو در نشست امروز نرخ بهره را بدون تغییر حفظ کرد.",
            "translation": "فدرال رزرو نرخ بهره را بدون تغییر حفظ کرد.",
            "needs_review": needs_review,
            "review_note": "بررسی نام مقام" if needs_review else "",
        }
        return [
            json_response({"data": {"id": "123"}}),
            json_response(
                {
                    "data": [
                        {
                            "id": "1900000000000000001",
                            "text": "Fed leaves interest rates unchanged.",
                            "created_at": "2026-11-04T08:30:00.000Z",
                            "lang": "en",
                        }
                    ]
                }
            ),
            json_response(
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": json.dumps(translation)}],
                        }
                    ],
                }
            ),
        ]

    @patch.dict("os.environ", env, clear=False)
    @patch("nicoption_dashboard.x_content.requests.request")
    def test_sync_creates_reviewable_article_draft_with_source_metadata(self, request):
        request.side_effect = self.upstream_responses()

        result = sync_x_account(username="financialjuice")

        self.assertEqual(result.discovered, 1)
        self.assertEqual(result.translated, 1)
        self.assertEqual(result.published, 0)
        post = XPostTranslation.objects.select_related("article").get()
        self.assertEqual(post.translation_status, XPostTranslation.TranslationStatus.TRANSLATED)
        self.assertEqual(post.translation_attempts, 1)
        self.assertFalse(post.article.is_published)
        self.assertEqual(post.article.slug, "financialjuice-1900000000000000001")
        self.assertIn("فدرال رزرو", post.article.body)

        x_request = request.call_args_list[1]
        self.assertEqual(x_request.kwargs["params"]["exclude"], "retweets,replies")
        openai_request = request.call_args_list[2]
        self.assertEqual(openai_request.args[1], "https://api.openai.com/v1/responses")
        self.assertEqual(
            openai_request.kwargs["json"]["text"]["format"]["type"],
            "json_schema",
        )

    @patch.dict("os.environ", env, clear=False)
    @patch("nicoption_dashboard.x_content.requests.request")
    def test_auto_publish_keeps_flagged_translation_in_draft(self, request):
        request.side_effect = self.upstream_responses(needs_review=True)

        result = sync_x_account(username="financialjuice", auto_publish=True)

        self.assertEqual(result.published, 0)
        self.assertFalse(Article.objects.get().is_published)

    @patch.dict("os.environ", env, clear=False)
    @patch("nicoption_dashboard.x_content.requests.request")
    def test_published_translation_is_returned_by_articles_api_with_original_source(self, request):
        request.side_effect = self.upstream_responses()
        sync_x_account(username="financialjuice", auto_publish=True)
        user = get_user_model().objects.create_user(username="reader")
        self.client.force_login(user)

        response = self.client.get("/api/articles")

        self.assertEqual(response.status_code, 200)
        article = response.json()["articles"][0]
        self.assertEqual(article["source"]["label"], "@financialjuice")
        self.assertEqual(article["source"]["original_text"], "Fed leaves interest rates unchanged.")
        self.assertEqual(
            article["source"]["url"],
            "https://x.com/financialjuice/status/1900000000000000001",
        )

    @patch.dict(
        "os.environ",
        {"X_BEARER_TOKEN": "x-test-token", "OPENAI_API_KEY": ""},
        clear=False,
    )
    @patch("nicoption_dashboard.x_content.requests.request")
    def test_missing_openai_key_does_not_consume_translation_attempts(self, request):
        XPostTranslation.objects.create(
            post_id="1900000000000000000",
            username="financialjuice",
            source_url="https://x.com/financialjuice/status/1900000000000000000",
            original_text="Markets await the central bank decision.",
            source_created_at=datetime(2026, 11, 4, 8, 0, tzinfo=dt_timezone.utc),
        )
        request.side_effect = [
            json_response({"data": {"id": "123"}}),
            json_response({"data": []}),
        ]

        with self.assertRaises(XContentConfigurationError):
            sync_x_account(username="financialjuice")

        post = XPostTranslation.objects.get()
        self.assertEqual(post.translation_attempts, 0)
        self.assertEqual(post.translation_status, XPostTranslation.TranslationStatus.PENDING)
