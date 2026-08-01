import unittest
from unittest.mock import patch

from scripts.reputation_monitor import load_watched_pages, page_snapshot, parse_news_rss


class ReputationMonitorTests(unittest.TestCase):
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
            self.assertEqual([], load_watched_pages())


if __name__ == "__main__":
    unittest.main()
