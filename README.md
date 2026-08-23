# jonvillasurdajr.github.io

Source for [jonvillasurdajr.github.io](https://jonvillasurdajr.github.io/), the professional site for Jon G. Villasurda Jr.

The Jekyll site presents a consistent professional profile, selected public work, and practical notes on Medicaid, behavioral health, CCBHC implementation, analytics, and program evaluation.

## SEO safeguards

- Unique titles and descriptions, self-referencing canonicals, Open Graph metadata, and crawlable JSON-LD
- A curated sitemap, permissive robots file, and IndexNow verification key
- Deployment-aware health checks that crawl every sitemap URL and validate internal links
- IndexNow submissions generated from the live sitemap after GitHub Pages publishes the current commit
- A daily technical SEO audit with automatic failure/recovery issues, including full-name, suffix, Mercer, Okemos, and corroborating-profile checks on the primary professional entity markup
- A daily external-reputation monitor with a primary run and two staggered recovery opportunities that search identity, professional, plea, offense, and headline variants in Google News and watch known publication pages
- Duplicate-safe recovery gating: later scheduled runs execute only when no earlier scheduled run has completed or remains active that day
- A persistent assigned status issue confirming each completed scan and identifying whether it was a primary, recovery, or manual run
- Historical CSV inventory, headline-change detection, stable article-body monitoring that excludes changing newsroom navigation, workflow summaries, and approval-gated correction-request drafts for new reputation findings or material watched-page changes; actionable issue entries link to prefilled Gmail drafts
- Monitoring-state recovery from both the Actions cache and retained run artifacts, preventing a routine cache miss from silently discarding observation history
- A daily review issue for Search Console, AI visibility, current references, and workflow continuity

The reputation monitor automatically preserves and classifies evidence, records previously observed results even after they leave the current Google News window, and flags later headline edits as separate review events. It does not send correction demands, Gmail messages, or make legal conclusions. Generated outreach text must be checked against the complete article and court record before it is sent.

The primary schedule is 12:23 UTC, with recovery opportunities at 13:53 UTC and 15:23 UTC. GitHub may delay any scheduled event; the recovery gate suppresses duplicate scans after an earlier run succeeds and labels a later scan as a recovery when it is needed. Successful scans update the assigned `Daily reputation monitor status` issue. Findings that need review update `External monitoring review needed`, where each actionable item includes a prefilled Gmail link. The full editable drafts, evidence, inventory, and restorable monitor state remain available for 30 days in each run artifact.

GitHub issue updates and workflow artifacts are the built-in daily digest path; the workflow does not send email automatically. To receive successful-run email, update the repository notification preference for Actions from “Failed workflows only” to “All activity” (or use a separate, explicitly configured mail provider). The scheduled scan itself remains approval-gated: it can prepare evidence and drafts, but it does not contact a publication or modify an external profile.

## Maintenance

GitHub may disable scheduled workflows in a public repository after 60 days without repository activity. The daily review workflow maintains a monthly default-branch heartbeat as a continuity safeguard and intentionally allows the normal site build to publish that revision. Substantive, accurate content updates remain preferable whenever there is genuine professional work to add.

Run the production audit locally with:

```shell
python scripts/seo_automation.py audit --sitemap https://jonvillasurdajr.github.io/sitemap.xml
```

Run the automation tests locally with:

```shell
python -m unittest discover -s tests -p "test_*.py"
```
