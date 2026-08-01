#!/usr/bin/env python3
"""Dependency-free checks and notifications for the deployed SEO contract."""
import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

USER_AGENT = "site-seo-automation/1.0"

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.meta={}; self.links=[]; self.h1=0; self.jsonld=[]; self.in_jsonld=False; self.in_title=False; self.data=[]; self.title_data=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag == "html":
            self.meta.setdefault("html:lang", []).append((a.get("lang") or "").strip())
        elif tag == "meta":
            key=(a.get("name") or a.get("property") or "").lower()
            if key: self.meta.setdefault(key,[]).append((a.get("content") or "").strip())
        elif tag == "link":
            relations=a.get("rel", "").lower().split()
            if "canonical" in relations: self.meta.setdefault("canonical",[]).append((a.get("href") or "").strip())
            if "icon" in relations: self.meta.setdefault("icon",[]).append((a.get("href") or "").strip())
            if "alternate" in relations and a.get("type", "").lower() == "application/atom+xml":
                self.meta.setdefault("alternate:atom",[]).append((a.get("href") or "").strip())
        elif tag == "a" and a.get("href"): self.links.append(a["href"].strip())
        elif tag == "h1": self.h1 += 1
        elif tag == "title": self.in_title=True; self.title_data=[]
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json": self.in_jsonld=True; self.data=[]
    def handle_data(self, data):
        if self.in_jsonld: self.data.append(data)
        if self.in_title: self.title_data.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.in_jsonld: self.jsonld.append("".join(self.data).strip()); self.in_jsonld=False
        elif tag == "title" and self.in_title: self.meta.setdefault("title",[]).append("".join(self.title_data).strip()); self.in_title=False

def clean(url):
    p=urlsplit(url); return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))

def fetch(url, timeout=20, attempts=3, method="GET", data=None, headers=None):
    """Bounded, retrying HTTP request returning final URL, status, and body."""
    err=None
    for number in range(attempts):
        try:
            req=Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
            with urlopen(req, timeout=timeout) as response:
                return clean(response.geturl()), response.status, response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
        except HTTPError as exc:
            detail=exc.read().decode("utf-8", "replace")[:500]; err=RuntimeError(f"{url}: HTTP {exc.code}: {detail}")
            if 400 <= exc.code < 500: break
        except (URLError, OSError, TimeoutError) as exc: err=RuntimeError(f"{url}: request failed: {exc}")
        if number + 1 < attempts: time.sleep(min(2 * (number + 1), 5))
    raise err

def read_sitemap(sitemap, timeout):
    _, status, xml=fetch(sitemap, timeout)
    if status != 200: raise RuntimeError(f"{sitemap}: expected 200, got {status}")
    try: root=ET.fromstring(xml)
    except ET.ParseError as exc: raise RuntimeError(f"{sitemap}: invalid XML: {exc}") from exc
    urls=[]; now=datetime.now(timezone.utc)+timedelta(days=1)
    for entry in root.findall(".//{*}url"):
        location=entry.find("{*}loc"); modified=entry.find("{*}lastmod")
        if location is None or not location.text or not location.text.strip():
            raise RuntimeError(f"{sitemap}: contains a URL entry without <loc>")
        url=clean(location.text.strip()); urls.append(url)
        if modified is None or not modified.text or not modified.text.strip():
            raise RuntimeError(f"{sitemap}: {url} is missing <lastmod>")
        raw=modified.text.strip()
        try:
            parsed=datetime.fromisoformat(raw.replace("Z","+00:00"))
            if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise RuntimeError(f"{sitemap}: {url} has invalid <lastmod> {raw!r}") from exc
        if parsed > now: raise RuntimeError(f"{sitemap}: {url} has future <lastmod> {raw!r}")
    if not urls: raise RuntimeError(f"{sitemap}: contains no <loc> URLs")
    host=urlsplit(sitemap).netloc.lower(); foreign=[u for u in urls if urlsplit(u).netloc.lower()!=host]
    if foreign: raise RuntimeError(f"{sitemap}: URLs outside {host}: {', '.join(foreign[:3])}")
    return list(dict.fromkeys(urls)), host

def value(meta, name, url, failures):
    results=[item.strip() for item in meta.get(name, []) if item.strip()]
    if not results:
        failures.append(f"{url}: missing or empty {name}")
        return ""
    if len(results) != 1:
        failures.append(f"{url}: expected one {name}, found {len(results)}")
    return results[0]

def page_audit(url, timeout, host):
    failures=[]; internal=[]
    try: final, status, html=fetch(url, timeout)
    except RuntimeError as exc: return url, [str(exc)], internal, None, None
    if status != 200: failures.append(f"{url}: expected 200, got {status}")
    if final != clean(url): failures.append(f"{url}: redirects to {final}; sitemap URLs must resolve directly")
    parser=Page(); parser.feed(html); parser.close()
    canonical=value(parser.meta,"canonical",url,failures); title=value(parser.meta,"title",url,failures); description=value(parser.meta,"description",url,failures)
    lang=value(parser.meta,"html:lang",url,failures)
    if lang and lang.lower() != "en-us": failures.append(f"{url}: expected html lang en-US, got {lang}")
    robots=value(parser.meta,"robots",url,failures).lower().replace(" ","")
    if robots and not {"index","follow"}.issubset(robots.split(",")): failures.append(f"{url}: robots must include index,follow (got {robots})")
    if parser.h1 != 1: failures.append(f"{url}: expected exactly one H1, found {parser.h1}")
    if canonical and clean(urljoin(final,canonical)) != final: failures.append(f"{url}: canonical does not match final URL {final}")
    if not parser.jsonld: failures.append(f"{url}: missing JSON-LD")
    schema_types=set(); schema_objects=[]
    for item in parser.jsonld:
        try:
            parsed=json.loads(item)
            objects=parsed if isinstance(parsed,list) else [parsed]
            for obj in objects:
                if isinstance(obj,dict):
                    schema_objects.append(obj)
                    if obj.get("@type"): schema_types.add(obj["@type"])
        except json.JSONDecodeError as exc: failures.append(f"{url}: invalid JSON-LD: {exc.msg}")
    if urlsplit(final).path == "/" and "ProfilePage" not in schema_types:
        failures.append(f"{url}: homepage must include ProfilePage JSON-LD")
    if urlsplit(final).path == "/":
        people=[obj for obj in schema_objects if obj.get("@type") == "Person"]
        if len(people) != 1:
            failures.append(f"{url}: homepage must include exactly one Person JSON-LD object")
        else:
            person=people[0]
            if person.get("name") != "Jon G. Villasurda Jr.": failures.append(f"{url}: Person name must be Jon G. Villasurda Jr.")
            if person.get("honorificSuffix") != "Jr.": failures.append(f"{url}: Person honorificSuffix must be Jr.")
            if len(person.get("sameAs") or []) < 3: failures.append(f"{url}: Person sameAs must contain at least three corroborating profiles")
            if not isinstance(person.get("image"),dict) or not person["image"].get("contentUrl"): failures.append(f"{url}: Person image must be an ImageObject with contentUrl")
            if not isinstance(person.get("hasCredential"),dict): failures.append(f"{url}: Person must include hasCredential")
    if urlsplit(final).path != "/" and "BreadcrumbList" not in schema_types:
        failures.append(f"{url}: missing BreadcrumbList JSON-LD")
    og_url=value(parser.meta,"og:url",url,failures); og_title=value(parser.meta,"og:title",url,failures); og_desc=value(parser.meta,"og:description",url,failures); og_image=value(parser.meta,"og:image",url,failures); icon=value(parser.meta,"icon",url,failures)
    atom=value(parser.meta,"alternate:atom",url,failures)
    if og_url and clean(urljoin(final,og_url)) != final: failures.append(f"{url}: og:url does not match final URL")
    if title and og_title and title != og_title: failures.append(f"{url}: og:title differs from title")
    if description and og_desc and description != og_desc: failures.append(f"{url}: og:description differs from description")
    for label, candidate in (("og:image", og_image), ("icon", icon)):
        if candidate and urlsplit(urljoin(final, candidate)).scheme not in ("http", "https"):
            failures.append(f"{url}: {label} must resolve to HTTP(S)")
    if atom and clean(urljoin(final,atom)) != clean(f"https://{host}/feed.xml"):
        failures.append(f"{url}: Atom feed link must resolve to https://{host}/feed.xml")
    for href in parser.links:
        absolute=clean(urljoin(final,href)); p=urlsplit(absolute)
        if p.scheme in ("http","https") and p.netloc.lower()==host: internal.append(absolute)
    return url, failures, internal, title, description

def discovery_audit(sitemap, timeout):
    """Validate crawler discovery files that are intentionally outside the sitemap."""
    failures=[]; parts=urlsplit(sitemap); root=f"{parts.scheme}://{parts.netloc}/"
    robots_url=urljoin(root,"robots.txt"); key_url=urljoin(root,"indexnow-key.txt"); feed_url=urljoin(root,"feed.xml")
    try:
        final,status,robots=fetch(robots_url,timeout)
        if final != clean(robots_url) or status != 200: failures.append(f"{robots_url}: expected a direct 200 response")
        if f"Sitemap: {sitemap}" not in robots: failures.append(f"{robots_url}: missing Sitemap: {sitemap}")
    except RuntimeError as exc: failures.append(str(exc))
    try:
        final,status,key=fetch(key_url,timeout)
        if final != clean(key_url) or status != 200: failures.append(f"{key_url}: expected a direct 200 response")
        if not re.fullmatch(r"[0-9a-fA-F-]{8,128}",key.strip()): failures.append(f"{key_url}: invalid IndexNow key format")
    except RuntimeError as exc: failures.append(str(exc))
    try:
        final,status,feed=fetch(feed_url,timeout)
        if final != clean(feed_url) or status != 200: failures.append(f"{feed_url}: expected a direct 200 response")
        feed_root=ET.fromstring(feed)
        if feed_root.tag != "{http://www.w3.org/2005/Atom}feed": failures.append(f"{feed_url}: expected an Atom feed")
        if not feed_root.findall("{http://www.w3.org/2005/Atom}entry"): failures.append(f"{feed_url}: contains no entries")
    except (RuntimeError, ET.ParseError) as exc: failures.append(f"{feed_url}: invalid Atom feed: {exc}")
    return failures

def wait_revision(args):
    if not args.expected_sha: print("No expected SHA supplied; skipping deployment revision wait."); return 0
    deadline=time.monotonic()+args.timeout; last="not found"
    while time.monotonic() < deadline:
        try:
            _,_,html=fetch(args.site, args.request_timeout, attempts=1); parser=Page(); parser.feed(html); last=(parser.meta.get("build-revision") or ["not found"])[0]
            if last == args.expected_sha: print(f"Deployment exposes build revision {args.expected_sha}."); return 0
        except RuntimeError as exc: last=str(exc)
        print(f"Waiting for {args.expected_sha}; live revision is {last}."); time.sleep(args.interval)
    raise RuntimeError(f"Timed out after {args.timeout}s waiting for {args.site} build-revision {args.expected_sha}; last value: {last}")

def audit(args):
    urls,host=read_sitemap(args.sitemap,args.request_timeout); print(f"Auditing {len(urls)} sitemap URLs on {host}.")
    failures=discovery_audit(args.sitemap,args.request_timeout); titles={}; descriptions={}; links=set()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(page_audit,url,args.request_timeout,host) for url in urls]
        for future in as_completed(futures):
            _,bad,page_links,title,description=future.result(); failures.extend(bad); links.update(page_links)
            if title: titles.setdefault(title,[]).append(_)
            if description: descriptions.setdefault(description,[]).append(_)
    for label,collection in (("title",titles),("description",descriptions)):
        for text,duplicates in collection.items():
            if len(duplicates)>1: failures.append(f"duplicate {label} {text!r}: {', '.join(duplicates)}")
    print(f"Checking {len(links)} internal links.")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(fetch,link,args.request_timeout):link for link in links}
        for future in as_completed(futures):
            link=futures[future]
            try:
                final,status,_=future.result()
                if status != 200: failures.append(f"internal link {link}: expected 200, got {status}")
                if final != clean(link): failures.append(f"internal link {link}: redirects to {final}")
            except RuntimeError as exc: failures.append(f"invalid internal link {link}: {exc}")
    if failures: print("SEO audit failed:\n- " + "\n- ".join(sorted(set(failures))),file=sys.stderr); return 1
    print("SEO audit passed."); return 0

def submit_indexnow(args):
    urls,host=read_sitemap(args.sitemap,args.request_timeout); key=Path(args.key_file).read_text(encoding="utf-8").strip()
    if not key: raise RuntimeError(f"{args.key_file}: IndexNow key is empty")
    key_location=f"https://{host}/indexnow-key.txt"
    _,_,live_key=fetch(key_location,args.request_timeout)
    if live_key.strip() != key: raise RuntimeError(f"{key_location}: live key does not match {args.key_file}")
    payload=json.dumps({"host":host,"key":key,"keyLocation":key_location,"urlList":urls}).encode()
    _,status,_=fetch(args.endpoint,args.request_timeout,method="POST",data=payload,headers={"Content-Type":"application/json"})
    if status not in (200,202): raise RuntimeError(f"IndexNow returned unexpected HTTP {status}")
    print(f"Submitted {len(urls)} sitemap URLs to IndexNow (HTTP {status})."); return 0

def main():
    parser=argparse.ArgumentParser(description=__doc__); commands=parser.add_subparsers(dest="command",required=True)
    wait=commands.add_parser("wait-revision"); wait.add_argument("--site",required=True); wait.add_argument("--expected-sha"); wait.add_argument("--timeout",type=int,default=600); wait.add_argument("--interval",type=int,default=15); wait.add_argument("--request-timeout",type=int,default=20); wait.set_defaults(func=wait_revision)
    check=commands.add_parser("audit"); check.add_argument("--sitemap",required=True); check.add_argument("--workers",type=int,default=8); check.add_argument("--request-timeout",type=int,default=20); check.set_defaults(func=audit)
    send=commands.add_parser("submit-indexnow"); send.add_argument("--sitemap",required=True); send.add_argument("--key-file",required=True); send.add_argument("--endpoint",default="https://www.bing.com/indexnow"); send.add_argument("--request-timeout",type=int,default=20); send.set_defaults(func=submit_indexnow)
    args=parser.parse_args()
    if any(getattr(args,name,1)<=0 for name in ("request_timeout","timeout","interval","workers")): parser.error("timeouts, interval, and workers must be positive")
    try: return args.func(args)
    except RuntimeError as exc: print(f"ERROR: {exc}",file=sys.stderr); return 1
if __name__ == "__main__": sys.exit(main())
