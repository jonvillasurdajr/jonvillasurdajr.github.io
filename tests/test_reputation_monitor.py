import unittest
from unittest.mock import patch

from scripts.reputation_monitor import (
    DEFAULT_QUERIES,
    attach_contact,
    classify_news_item,
    is_relevant_news_item,
    load_watched_pages,
    page_snapshot,
    parse_news_rss,
)


class ReputationMonitorTests(unittest.TestCase):
    def test_default_queries_cover_identity_and_plea_variants(self):
        joined = "\n".join(DEFAULT_QUERIES)
        self.assertIn('"Jon Granger Villasurda"', joined)
        self.assertIn('"Jon G. Villasurda Jr."', joined)
        self.assertIn("Mercer", joined)
        self.assertIn("sentencing", joined)
        self.assertIn("prostitution", joined)
        self.assertIn("trafficking", joined)

    def test_parses_google_news_items(self):
        xml = """<rss><channel><item>
          <title>Example result</title>
          <link>https://news.google.com/example</link>
          <guid>example-id</guid>
          <pubDate>Fri, 31 Jul 2026 12:00:00 GMT</pubDate>
          <source>Example News</source>
        </item></channel></rss>"""
        items = parse_news_rss(xml, '"Example Name"')
        self.assertEqual(1, len(items))
        self.assertEqual("example-id", items[0]["id"])
        self.assertEqual("Example News", items[0]["source"])

    def test_filters_unrelated_exact_query_match(self):
        item = {
            "title": "Michigan State basketball travels to UConn for an exhibition game - Facebook",
            "source": "facebook.com",
        }
        self.assertFalse(is_relevant_news_item(item))

    def test_keeps_case_headline_that_omits_name(self):
        item = {
            "title": "Clinton Township man pleads guilty in connection with human trafficking ring",
            "source": "Example News",
        }
        self.assertTrue(is_relevant_news_item(item))

    def test_keeps_professional_headline_that_omits_name(self):
        item = {
            "title": "Mercer leader discusses behavioral health access in Michigan",
            "source": "Example News",
        }
        self.assertTrue(is_relevant_news_item(item))

    def test_page_snapshot_tracks_metadata_and_name_context(self):
        html = """<html><head><title>Updated report</title>
        <meta name="description" content="A precise update">
        <meta property="og:title" content="Updated social title">
        </head><body><p>The report identifies Jon Villasurda Sr. consistently.</p></body></html>"""
        snapshot = page_snapshot("Example", "https://example.com", "https://example.com", html)
        self.assertEqual("Updated report", snapshot["title"])
        self.assertEqual("A precise update", snapshot["description"])
        self.assertIn("Jon Villasurda Sr.", snapshot["contexts"][0])
        self.assertEqual(64, len(snapshot["fingerprint"]))

    def test_missing_or_empty_watch_secret_means_no_watched_pages(self):
        with patch.dict("os.environ", {"REPUTATION_WATCH_URLS_JSON": ""}):
            self.assertEqual([], load_watched_pages("missing-config.json"))

    def test_classifies_suffix_omission_as_high_priority(self):
        item = {
            "title": "Jon Villasurda named in new report",
            "link": "https://example.com/story",
            "source": "Example",
            "published": "2026-08-01",
            "query": '"Jon Villasurda"',
        }
        classified = classify_news_item(item)
        self.assertEqual("high", classified["priority"])
        self.assertIn("suffix", classified["issues"][0].lower())

    def test_classifies_ambiguous_trafficking_plea_headline(self):
        item = {
            "title": "Clinton Township man pleads guilty in human trafficking ring",
            "link": "https://example.com/story",
            "source": "Example",
            "published": "2026-08-01",
            "query": '"Jon Villasurda"',
        }
        classified = classify_news_item(item)
        self.assertEqual("high", classified["priority"])
        self.assertIn("plea-characterization", classified["issues"][0].lower())

    def test_verified_contact_creates_prefilled_gmail_link(self):
        item = {
            "title": "Example",
            "link": "https://example.com/story",
            "source": "WDIV",
        }
        enriched = attach_contact(item, [{"match": "WDIV", "email": "news@example.com"}])
        self.assertEqual("news@example.com", enriched["contact_email"])
        self.assertIn("mail.google.com/mail/", enriched["gmail_draft_url"])
        self.assertIn("news%40example.com", enriched["gmail_draft_url"])


if __name__ == "__main__":
    unittest.main()
