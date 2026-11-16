from django.test import SimpleTestCase, override_settings

from nicoption_dashboard.amar_mcp import RELEASE_SEARCHES, TOPICS, collect_amar_snapshot


class FakeAmarClient:
    calls = []

    def __init__(self, command, timeout):
        self.command = command
        self.timeout = timeout

    def __enter__(self):
        type(self).calls = []
        return self

    def __exit__(self, *args):
        return None

    def initialize(self):
        return {"serverInfo": {"name": "amar-mcp", "version": "0.1.1"}}

    def call_tool(self, name, arguments):
        type(self).calls.append((name, arguments))
        if name == "am_indicators" and "table" not in arguments:
            return {
                "source": {"release": 100},
                "tables": [{"n": 1, "title": f"جدول {arguments['topic']}"}],
            }
        if name == "am_indicators":
            return {
                "tables": [{
                    "title": f"جدول {arguments['topic']}",
                    "source": "مرکز آمار ایران",
                    "columns": ["مقدار"],
                    "total_rows": 1,
                    "rows": [["۱۴۰۴", 12]],
                }]
            }
        if name == "am_search":
            if arguments["query"] == "گردشگری":
                return {"results": [{"id": 21835, "title": "سری زمانی تعداد سفرها", "period": "بهار تا تابستان", "frequency": "فصلی"}]}
            return {"results": [{"id": 1, "title": arguments["query"]}]}
        if name == "am_table":
            return {"release": "سری زمانی سفر", "rows": [[1, "عنوان"], [2, "سفر", 1387, 1387], [3, None, "بهار", "تابستان"], [4, "سفر رفته", 10, 12]]}
        return {"tool": name, "arguments": arguments}


class AmarMcpCollectionTests(SimpleTestCase):
    @override_settings(AMAR_MCP_COMMAND="uvx amar-mcp", AMAR_MCP_TIMEOUT_SECONDS=45)
    def test_collects_both_topic_collections_and_release_searches(self):
        result = collect_amar_snapshot(client_class=FakeAmarClient)

        self.assertEqual(result.server_name, "amar-mcp")
        self.assertEqual(result.server_version, "0.1.1")
        self.assertEqual(set(result.payload["macro"]), set(TOPICS))
        self.assertEqual(set(result.payload["releases"]), {item[0] for item in RELEASE_SEARCHES})
        self.assertEqual(result.errors, {})
        self.assertEqual(len(result.payload["travel_tables"]), 1)
        self.assertEqual(result.payload["travel_tables"][0]["id"], 21835)
        self.assertTrue(all(len(topic["tables"]) == 1 for topic in result.payload["macro"].values()))
        self.assertEqual(
            sum(name == "am_indicators" and "table" in arguments for name, arguments in FakeAmarClient.calls),
            len(TOPICS),
        )

    def test_topic_metadata_keeps_new_and_complementary_sets_explicit(self):
        collections = {item["collection"] for item in TOPICS.values()}

        self.assertEqual(collections, {"new", "complementary"})
        self.assertEqual(sum(item["collection"] == "new" for item in TOPICS.values()), 8)
        self.assertEqual(sum(item["collection"] == "complementary" for item in TOPICS.values()), 3)
