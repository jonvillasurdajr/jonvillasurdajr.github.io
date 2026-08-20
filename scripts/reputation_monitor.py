#!/usr/bin/env python3
"""Monitor exact-name news results and selected pages without publishing them."""

import argparse
import csv
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
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

USER_AGENT = "jon-villasurda-reputation-watch/1.0"
DEFAULT_QUERIES = (
    '"Jon Villasurda"',
    '"Jon G. Villasurda Jr."',
    '"Jon Villasurda Jr"',
    '"Jon Villasurda Sr"',
    '"Jon Granger Villasurda"',
    '"Jon Villasurda" (Mercer OR Okemos OR CCBHC)',
    '"Jon Villasurda" (pleaded OR pled OR guilty OR sentencing)',
    '"Jon Villasurda" (prostitution OR trafficking)',
    '"Jon Villasurda" ("human trafficking case" OR "transporting a person for prostitution")',
    '"Jon Villasurda" (headline OR article OR news OR publication)',
)

PLEA_TERMS = re.compile(r"\b(plead(?:ed|s)?|pled|guilty|convict(?:ed|ion)?)\b", re.I)
TRAFFICKING_TERMS = re.compile(r"\b(?:human|sex)[ -]?trafficking\b|trafficking ring", re.I)
OFFENSE_TERMS = re.compile(r"transport(?:ing|ation)? (?:a person |women? )?for (?:the purposes? of )?prostitution", re.I)
DISPOSITION_TERMS = re.compile(r"\b(?:sentenc(?:e|ed|ing)|probation|prison)\b", re.I)
PROFESSIONAL_TERMS = re.compile(r"\b(?:mercer|okemos|ccbhc|healthcare|health care|behavioral health)\b", re.I)
PAGE_MATERIAL_TERMS = re.compile(
    r"\bvillasurda\b|\b(?:plead(?:ed|s)?|pled|guilty|convict(?:ed|ion)?)\b|"
    r"transport(?:ing|ation)?|prostitution|(?:human|sex)[ -]?trafficking|trafficking ring|"
    r"\b(?:sentenc(?:e|ed|ing)|probation|prison)\b",
    re.I,
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
            # A stable link-based fallback lets the monitor detect a changed
            # headline instead of treating the revised result as a new story.
            "id": guid or stable_key(link),
            "query": query,
            "title": title,
            "link": link,
            "source": source,
            "published": published_iso,
        })
    return results


def is_relevant_news_item(item):
    """Reject unrelated Google News matches while retaining identity and case coverage."""
    title = item.get("title", "")
    if re.search(r"\bvillasurda\b", title, re.I):
        return True
    if PROFESSIONAL_TERMS.search(title):
        return True
    case_context = TRAFFICKING_TERMS.search(title) or OFFENSE_TERMS.search(title)
    return bool(case_context and (PLEA_TERMS.search(title) or DISPOSITION_TERMS.search(title)))


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


def material_contexts(text, radius=360, limit=20):
    """Keep stable legal/identity sentences and drop navigation boilerplate."""
    sentences = [normalized(sentence) for sentence in re.split(r"(?<=[.!?])\s+", text)]
    contexts = []
    for sentence in sentences:
        if not sentence or not PAGE_MATERIAL_TERMS.search(sentence):
            continue
        if sentence not in contexts:
            contexts.append(sentence)
    if contexts:
        return contexts[:limit]
    return relevant_context(text, radius=radius)[:limit]


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
        "contexts": material_contexts(visible_text),
    }
    snapshot["fingerprint"] = stable_key(json.dumps(snapshot, sort_keys=True, ensure_ascii=False))
    return snapshot


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def classify_news_item(item):
    """Assign a review priority without asserting that publication text is false."""
    title = item.get("title", "")
    lowered = title.lower()
    issues = []
    priority = "low"

    if "jon villasurda" in lowered and not any(
        variant in lowered for variant in ("jon villasurda sr", "jon villasurda jr", "jon granger villasurda")
    ):
        issues.append("Shared-name ambiguity: the result omits a generational suffix.")
        priority = "high"

    if "federal charge" in lowered:
        issues.append("Jurisdiction check: verify any reference to federal charges against the state-court record.")
        priority = "critical"

    if PLEA_TERMS.search(title) and TRAFFICKING_TERMS.search(title):
        if OFFENSE_TERMS.search(title):
            issues.append("Framing check: the specific prostitution-transportation count and broader trafficking context appear together.")
            priority = max_priority(priority, "medium")
        else:
            issues.append("Plea-characterization check: the headline mentions trafficking without naming the offense of conviction.")
            priority = max_priority(priority, "high")

    if re.search(r"\b(sentenced|sentence|probation|prison)\b", title, re.I):
        issues.append("Disposition check: confirm the reported sentence against the final court order.")
        priority = max_priority(priority, "high")

    if not issues:
        issues.append("New exact-name result; review for identity accuracy and relevance.")

    return {
        **item,
        "priority": priority,
        "issues": issues,
        "recommended_action": recommended_action(priority),
    }


def recommended_action(priority):
    return {
        "critical": "Preserve screenshots and court evidence; obtain legal review before escalation.",
        "high": "Verify the full article and metadata, then prepare a narrow factual correction request.",
        "medium": "Review the full context and consider a clarification request if readers could infer the wrong conviction.",
        "low": "Log the result and monitor; no outreach unless the full text reveals an issue.",
    }[priority]


def max_priority(left, right):
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return left if order[left] >= order[right] else right


def load_contacts(path):
    if not path or not Path(path).exists():
        return []
    contacts = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(contacts, list):
        raise RuntimeError("Media contacts configuration must be a JSON list")
    return contacts


def attach_contact(item, contacts):
    haystack = f"{item.get('source', '')} {item.get('title', '')}".lower()
    match = next((contact for contact in contacts if contact.get("match", "").lower() in haystack), None)
    if not match:
        return {**item, "contact_email": "", "gmail_draft_url": ""}
    subject = "Request for factual clarification and name disambiguation"
    body = (
        f"Hello {match.get('salutation', 'newsroom')},\n\n"
        f"I am writing to request a narrow factual review of this publication:\n{item['link']}\n\n"
        "The defendant is my father, Jon Villasurda Sr.; I am Jon Villasurda Jr., a separate individual. "
        "Please use the ‘Sr.’ suffix consistently wherever his name appears. Please also confirm that the headline, "
        "article text, captions, and social metadata distinguish the offense of conviction—transporting a person for "
        "prostitution—from the government’s characterization of the broader investigation. This request does not "
        "challenge accurate reporting about the case and is intended only to prevent identity confusion and ensure "
        "precision about the court disposition.\n\nThank you,\nJon Villasurda Jr."
    )
    query = urlencode({"view": "cm", "fs": "1", "to": match["email"], "su": subject, "body": body})
    return {**item, "contact_email": match["email"], "gmail_draft_url": f"https://mail.google.com/mail/?{query}"}


def write_inventory(path, items):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "priority", "published", "source", "title", "url", "query",
            "review_issues", "recommended_action", "contact_email", "gmail_draft_url",
            "status", "first_seen", "last_seen",
        ])
        for item in items:
            writer.writerow([
                item.get("priority", "low"), item.get("published", ""), item.get("source", ""),
                item.get("title", ""), item.get("link", ""), item.get("query", ""),
                " | ".join(item.get("issues", [])), item.get("recommended_action", ""),
                item.get("contact_email", ""), item.get("gmail_draft_url", ""),
                item.get("status", ""), item.get("first_seen", ""), item.get("last_seen", ""),
            ])


def correction_draft(item):
    issues = " ".join(item["issues"])
    return [
        f"### {item['title']}",
        "",
        f"- Priority: **{item['priority']}**",
        f"- Source: {item['source'] or 'Unknown'}",
        f"- URL: {item['link']}",
        f"- Review basis: {issues}",
        f"- Detection: {item.get('status', 'new')}",
        f"- Suggested recipient: {item.get('contact_email') or 'Contact research required'}",
        f"- [Open prefilled Gmail draft]({item['gmail_draft_url']})" if item.get("gmail_draft_url") else "- Gmail link unavailable until a verified contact is added.",
        "",
        "**Draft — verify the complete publication and court record before sending**",
        "",
        "Subject: Request for factual clarification and name disambiguation",
        "",
        "Hello,",
        "",
        "I am writing to request a narrow factual review of the publication linked above. "
        "The defendant is my father, Jon Villasurda Sr.; I am Jon Villasurda Jr., a separate individual. "
        "Please use the ‘Sr.’ suffix consistently wherever his name appears. Please also confirm that the headline, "
        "article text, captions, and social metadata distinguish the offense of conviction—transporting a person for "
        "prostitution—from the government’s characterization of the broader investigation. This request does not "
        "challenge accurate reporting about the case and is intended only to prevent identity confusion and ensure "
        "precision about the court disposition.",
        "",
        "Thank you for reviewing this request.",
        "",
        "Jon Villasurda Jr.",
        "",
    ]


def write_drafts(path, triage_items):
    lines = [
        "# Approval-gated correction request drafts",
        "",
        "These drafts are generated for review only. No message has been sent. New results and changed headlines are included when they need review.",
        "",
    ]
    actionable = [item for item in triage_items if item["priority"] in ("critical", "high", "medium")]
    if not actionable:
        lines.extend(["No actionable draft was generated in this run.", ""])
    for item in actionable:
        lines.extend(correction_draft(item))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_report(path, baseline, triage_items, changed_pages, errors, headline_changes=None):
    headline_changes = headline_changes or []
    lines = [
        "# External reputation monitoring report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    if baseline:
        lines.extend(["Initial baseline established; no alert was generated.", ""])
    lines.extend([
        f"New news results: **{len(triage_items)}**",
        f"Headline changes on watched results: **{len(headline_changes)}**",
        f"Changed watched pages: **{len(changed_pages)}**",
        "",
    ])
    if triage_items:
        lines.append("## New exact-name news results")
        lines.append("")
        for item in triage_items:
            source = f" - {item['source']}" if item["source"] else ""
            lines.extend([
                f"### [{item['title']}]({item['link']})",
                "",
                f"- Priority: **{item['priority']}**{source}",
                f"- Published: {item['published']}",
                f"- Review issue: {' '.join(item['issues'])}",
                f"- Recommended action: {item['recommended_action']}",
                f"- [Open prefilled Gmail draft]({item['gmail_draft_url']})" if item.get("gmail_draft_url") and item["priority"] != "low" else "- No outreach draft recommended for this item." if item["priority"] == "low" else "- Verified recipient still needed before outreach.",
                "",
            ])
        lines.append("")
    if headline_changes:
        lines.append("## Headline changes on previously observed results")
        lines.append("")
        for item in headline_changes:
            source = f" - {item['source']}" if item["source"] else ""
            lines.extend([
                f"### [{item['title']}]({item['link']})",
                "",
                f"- Priority: **{item['priority']}**{source}",
                f"- First observed: {item.get('first_seen', 'unknown')}",
                f"- Previously observed headline: {item.get('previous_title', 'unknown')}",
                f"- Review issue: {' '.join(item['issues'])}",
                f"- Recommended action: {item['recommended_action']}",
                f"- [Open prefilled Gmail draft]({item['gmail_draft_url']})" if item.get("gmail_draft_url") and item["priority"] != "low" else "- Verify before any outreach; no message was sent.",
                "",
            ])
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


def load_watched_pages(config_path=None):
    raw = os.environ.get("REPUTATION_WATCH_URLS_JSON")
    if not raw and config_path and Path(config_path).exists():
        raw = Path(config_path).read_text(encoding="utf-8")
    raw = raw or "[]"
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


def history_entry(value):
    """Read both the legacy first-seen timestamp and the richer history record."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        return {"first_seen": value, "last_seen": value}
    return {}


def headlines_differ(previous_title, current_title):
    return bool(
        previous_title
        and normalized(previous_title).casefold() != normalized(current_title).casefold()
    )


def monitor(args):
    state = read_json(args.state, {"seen_news": {}, "pages": {}, "errors": []})
    baseline = not Path(args.state).exists()
    errors = []
    current_news = []
    contacts = load_contacts(args.contacts)
    for query in args.query or DEFAULT_QUERIES:
        try:
            _, xml = fetch(news_url(query), args.timeout)
            current_news.extend(parse_news_rss(xml, query))
        except (OSError, ET.ParseError) as exc:
            errors.append(f"News query {query!r}: {exc}")

    relevant_news = [item for item in current_news if is_relevant_news_item(item)]
    deduplicated_news = {item["id"]: item for item in relevant_news}
    now = datetime.now(timezone.utc).isoformat()
    stored_news = state.get("seen_news", {})
    if not isinstance(stored_news, dict):
        stored_news = {}
    seen_news = dict(stored_news)
    new_news = []
    headline_changes = []
    inventory_items = []
    current_keys = set()

    for key, item in deduplicated_news.items():
        # Older state files used a title-plus-link hash when RSS omitted a
        # guid. Migrate that record quietly so deployment does not create a
        # false burst of new alerts.
        legacy_key = stable_key(item["title"], item["link"])
        record_key = key if key in stored_news else legacy_key if legacy_key in stored_news else None
        previous = history_entry(stored_news.get(record_key)) if record_key else {}
        known = record_key is not None
        previous_title = previous.get("last_title", "")

        if baseline:
            status = "baseline"
        elif not known:
            status = "new"
        elif headlines_differ(previous_title, item["title"]):
            status = "headline_change"
        else:
            status = "known"

        classified = attach_contact(classify_news_item(item), contacts)
        if status == "headline_change":
            classified["issues"] = [
                "Headline changed since the previous observation; compare the current headline with the article body and court disposition.",
                *classified["issues"],
            ]
            classified["priority"] = max_priority(classified["priority"], "medium")
            classified["recommended_action"] = recommended_action(classified["priority"])
            classified["previous_title"] = previous_title

        classified.update({
            "status": status,
            "first_seen": previous.get("first_seen") or now,
            "last_seen": now,
        })
        inventory_items.append(classified)
        current_keys.add(key)

        seen_news[key] = {
            "first_seen": classified["first_seen"],
            "last_seen": now,
            "last_title": item["title"],
            "last_link": item["link"],
            "source": item.get("source", ""),
            "published": item.get("published", ""),
            "query": item.get("query", ""),
            "priority": classified["priority"],
            "issues": classified["issues"],
            "recommended_action": classified["recommended_action"],
            "contact_email": classified.get("contact_email", ""),
        }
        if record_key and record_key != key:
            seen_news.pop(record_key, None)

        if status == "new":
            new_news.append(classified)
        elif status == "headline_change":
            headline_changes.append(classified)

    # Keep previously observed results in the CSV even after they fall out of
    # the current RSS window, so the artifact is an inventory rather than a
    # one-day alert list.
    for key, raw_record in seen_news.items():
        if key in current_keys:
            continue
        record = history_entry(raw_record)
        if not record.get("last_title") or not record.get("last_link"):
            continue
        inventory_items.append({
            "priority": record.get("priority", "low"),
            "published": record.get("published", ""),
            "source": record.get("source", ""),
            "title": record["last_title"],
            "link": record["last_link"],
            "query": record.get("query", ""),
            "issues": record.get("issues", []),
            "recommended_action": record.get("recommended_action", recommended_action(record.get("priority", "low"))),
            "contact_email": record.get("contact_email", ""),
            "status": "historical",
            "first_seen": record.get("first_seen", ""),
            "last_seen": record.get("last_seen", ""),
        })

    page_state = dict(state.get("pages", {}))
    changed_pages = []
    for page in load_watched_pages(args.watch_config):
        try:
            final_url, html = fetch(page["url"], args.timeout)
            snapshot = page_snapshot(page["label"], page["url"], final_url, html)
            previous = page_state.get(page["label"])
            if previous and previous.get("fingerprint") != snapshot["fingerprint"]:
                changed_pages.append(snapshot)
            page_state[page["label"]] = snapshot
        except OSError as exc:
            errors.append(f"Watched page {page['label']!r}: {exc}")

    previous_errors = set(state.get("errors", []))
    new_errors = [error for error in errors if error not in previous_errors]

    new_state = {
        "updated_at": now,
        "seen_news": seen_news,
        "pages": page_state,
        "errors": errors,
    }
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    Path(args.state).write_text(json.dumps(new_state, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(args.report, baseline, new_news, changed_pages, errors, headline_changes)
    write_inventory(args.inventory, inventory_items)
    write_drafts(args.drafts, new_news + headline_changes)
    alert_count = len(new_news) + len(headline_changes) + len(changed_pages)
    review_count = alert_count + len(new_errors)
    action_items = new_news + headline_changes
    write_outputs(args.github_output, {
        "alert_count": alert_count,
        "review_count": review_count,
        "new_news_count": len(new_news),
        "headline_change_count": len(headline_changes),
        "changed_page_count": len(changed_pages),
        "baseline": str(baseline).lower(),
        "error_count": len(errors),
        "new_error_count": len(new_errors),
        "critical_count": sum(item["priority"] == "critical" for item in action_items),
        "high_priority_count": sum(item["priority"] in ("critical", "high") for item in action_items),
    })
    print(
        f"Reputation watch completed: {alert_count} change(s), {len(headline_changes)} headline change(s), "
        f"{len(errors)} retrieval error(s), {len(new_errors)} newly observed error(s)."
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=".cache/reputation-watch.json")
    parser.add_argument("--report", default=".cache/reputation-watch-report.md")
    parser.add_argument("--inventory", default=".cache/reputation-watch-inventory.csv")
    parser.add_argument("--drafts", default=".cache/reputation-watch-drafts.md")
    parser.add_argument("--watch-config", default="config/reputation-watch.json")
    parser.add_argument("--contacts", default="config/media-contacts.json")
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
