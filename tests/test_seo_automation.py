import json
import unittest
from unittest import mock

from scripts import seo_automation


HOME_URL = "https://jonvillasurdajr.github.io/"


def homepage_html(alternate_names=None):
    alternate_names = alternate_names or [
        "Jon G. Villasurda Jr.",
        "Jon G Villasurda Jr",
        "Jon Villasurda",
        "Jon Villasurda Jr.",
    ]
    person = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Jon G. Villasurda Jr.",
        "additionalName": "G.",
        "honorificSuffix": "Jr.",
        "identifier": "jon-g-villasurda-jr",
        "alternateName": alternate_names,
        "worksFor": {"@type": "Organization", "name": "Mercer"},
        "workLocation": {
            "@type": "Place",
            "address": {"@type": "PostalAddress", "addressLocality": "Okemos", "addressRegion": "MI"},
        },
        "sameAs": [
            "https://github.com/jonvillasurdajr",
            "https://www.linkedin.com/in/jonvillasurdajr/",
            "https://chrt.org/bio/jon-villasurda/",
        ],
        "image": {"@type": "ImageObject", "contentUrl": "https://jonvillasurdajr.github.io/assets/images/jon-g-villasurda-jr-headshot.jpg"},
        "hasCredential": {"@type": "EducationalOccupationalCredential", "name": "Master of Public Health"},
    }
    return f'''<!doctype html>
<html lang="en-US"><head>
<title>Jon G. Villasurda Jr. | Mercer Government, Okemos MI</title>
<meta name="description" content="Official professional site" />
<meta name="robots" content="index,follow" />
<link rel="canonical" href="{HOME_URL}" />
<link rel="alternate" type="application/atom+xml" href="{HOME_URL}feed.xml" />
<link rel="icon" href="{HOME_URL}assets/images/jon-g-villasurda-jr-headshot.jpg" />
<meta property="og:url" content="{HOME_URL}" />
<meta property="og:title" content="Jon G. Villasurda Jr. | Mercer Government, Okemos MI" />
<meta property="og:description" content="Official professional site" />
<meta property="og:image" content="{HOME_URL}assets/images/jon-g-villasurda-jr-headshot.jpg" />
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"ProfilePage"}}</script>
<script type="application/ld+json">{json.dumps(person)}</script>
</head><body><h1>Jon G. Villasurda Jr.</h1></body></html>'''


class HomepageIdentityAuditTests(unittest.TestCase):
    def audit(self, html):
        with mock.patch.object(seo_automation, "fetch", return_value=(HOME_URL, 200, html)):
            return seo_automation.page_audit(HOME_URL, timeout=1, host="jonvillasurdajr.github.io")[1]

    def test_homepage_has_required_identity_signals(self):
        self.assertEqual(self.audit(homepage_html()), [])

    def test_homepage_requires_full_name_variant(self):
        failures = self.audit(homepage_html(["Jon G. Villasurda Jr.", "Jon Villasurda", "Jon Villasurda Jr."]))
        self.assertIn(
            f"{HOME_URL}: Person alternateName is missing identity variants: Jon G Villasurda Jr",
            failures,
        )


if __name__ == "__main__":
    unittest.main()
