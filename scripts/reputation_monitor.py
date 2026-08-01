#!/usr/bin/env python3
"""Monitor exact-name news results and selected pages without publishing them."""

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

USER_AGENT = "jon-villasurda-reputation-watch/1.0"
DEFAULT_QUERIES = (
    '"Jon Villasurda"',
    '"Jon Villasurda Jr"',
    '"Jon Villasurda Sr"',
)


def fetch(url, timeout=30):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
        return response.geturl(), body


def news_url(query):
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def stable_key(*parts):
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def parse_news_rss(xml, query):
    root = ET.fromstring(xml)
    results = []
    for item in root.findall(".//item"):
        def value(name):
            node = item.find(name)
            return (node.text or "").strip() if node is not None else ""

        title = value("title")
        link = value("link")
        guid = value("guid")
        published = value("pubDate")
        source_node = item.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        if not title or not link:
            continue
        try:
            published_iso = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            published_iso = published
        results.append({
            "id": guid or stable_key(title, link),
            "query": query,
            "title": title,
            "link": link,
            "source": source,
            "published": published_iso,
        })
    return results


class RelevantPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = []
        self.text = []
        self.in_title = False
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (attributes.get("name") or attributes.get("property") or "").lower()
            if key in ("description", "og:title", "og:description"):
                self.meta[key] = (attributes.get("content") or "").strip()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title.append(data)
        self.text.append(data)


def normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def relevant_context(text, term="villasurda", radius=280):
    lowered = text.lower()
    contexts = []
    cursor = 0
    while True:
        position = lowered.find(term, cursor)
        if position < 0:
            break
        excerpt = normalized(text[max(0, position - radius):position + len(term) + radius])
        if excerpt and excerpt not in contexts:
            contexts.append(excerpt)
        cursor = position + len(term)
    return contexts[:12]


def page_snapshot(label, requested_url, final_url, html):
    parser = RelevantPageParser()
    parser.feed(html)
    parser.close()
    visible_text = normalized(" ".join(parser.text))
    snapshot = {
        "label": label,
        "requested_url": requested_url,
        "final_url": final_url,
        "title": normalized(" ".join(parser.title)),
        "description": parser.meta.get("description", ""),
        "og_title": parser.meta.get("og:title", ""),
        "og_description": parser.meta.get("og:description", ""),
        "contexts": relevant_context(visible_text),
    }
    snapshot["fingerprint"] = stable_key(json.dumps(snapshot, sort_keys=True, ensure_ascii=False))
    return snapshot


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_report(path, baseline, new_news, changed_pages, errors):
    lines = [
        "# External reputation monitoring report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    if baseline:
        lines.extend(["Initial baseline established; no alert was generated.", ""])
    lines.extend([f"New news results: **{len(new_news)}**", f"Changed watched pages: **{len(changed_pages)}**", ""])
    if new_news:
        lines.append("## New exact-name news results")
        lines.append("")
        for item in new_news:
            source = f" - {item['source']}" if item["source"] else ""
            lines.append(f"- [{item['title']}]({item['link']}){source} ({item['published']})")
        lines.append("")
    if changed_pages:
        lines.append("## Changed watched pages")
        lines.append("")
        for page in changed_pages:
            lines.extend([
                f"### {page['label']}",
                "",
                f"- URL: {page['final_url']}",
                f"- Title: {page['title']}",
                f"- Description: {page['description']}",
                f"- Open Graph title: {page['og_title']}",
                f"- Open Graph description: {page['og_description']}",
                "",
                "Relevant on-page excerpts:",
                "",
            ])
            lines.extend(f"- {excerpt}" for excerpt in page["contexts"])
            lines.append("")
    if errors:
        lines.extend(["## Retrieval errors", ""])
        lines.extend(f"- {error}" for error in errors)
        lines.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_outputs(path, values):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def load_watched_pages():
    raw = os.environ.get("REPUTATION_WATCH_URLS_JSON") or "[]"
    try:
        pages = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"REPUTATION_WATCH_URLS_JSON is invalid JSON: {exc}") from exc
    if not isinstance(pages, list):
        raise RuntimeError("REPUTATION_WATCH_URLS_JSON must be a JSON list")
    for page in pages:
        if not isinstance(page, dict) or not page.get("label") or not page.get("url"):
            raise RuntimeError("Each watched page must contain label and url")
    return pages


def monitor(args):
    state = read_json(args.state, {"seen_news": {}, "pages": {}})
    baseline = not Path(args.state).exists()
    errors = []
    current_news = []
    for query in args.query or DEFAULT_QUERIES:
        try:
            _, xml = fetch(news_url(query), args.timeout)
            current_news.extend(parse_news_rss(xml, query))
        except (OSError, ET.ParseError) as exc:
            errors.append(f"News query {query!r}: {exc}")

    deduplicated_news = {item["id"]: item for item in current_news}
    new_news = [] if baseline else [
        item for key, item in deduplicated_news.items() if key not in state.get("seen_news", {})
    ]
    now = datetime.now(timezone.utc).isoformat()
    seen_news = dict(state.get("seen_news", {}))
    for key in deduplicated_news:
        seen_news.setdefault(key, now)

    page_state = dict(state.get("pages", {}))
    changed_pages = []
    for page in load_watched_pages():
        try:
            final_url, html = fetch(page["url"], args.timeout)
            snapshot = page_snapshot(page["label"], page["url"], final_url, html)
            previous = page_state.get(page["label"])
            if previous and previous.get("fingerprint") != snapshot["fingerprint"]:
                changed_pages.append(snapshot)
            page_state[page["label"]] = snapshot
        except OSError as exc:
            errors.append(f"Watched page {page['label']!r}: {exc}")

    new_state = {
        "updated_at": now,
        "seen_news": seen_news,
        "pages": page_state,
    }
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    Path(args.state).write_text(json.dumps(new_state, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(args.report, baseline, new_news, changed_pages, errors)
    alert_count = len(new_news) + len(changed_pages)
    review_count = alert_count + len(errors)
    write_outputs(args.github_output, {
        "alert_count": alert_count,
        "review_count": review_count,
        "new_news_count": len(new_news),
        "changed_page_count": len(changed_pages),
        "baseline": str(baseline).lower(),
        "error_count": len(errors),
    })
    print(f"Reputation watch completed: {alert_count} change(s), {len(errors)} retrieval error(s).")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=".cache/reputation-watch.json")
    parser.add_argument("--report", default=".cache/reputation-watch-report.md")
    parser.add_argument("--query", action="append")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        return monitor(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
