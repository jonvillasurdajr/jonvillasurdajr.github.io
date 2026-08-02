# jonvillasurdajr.github.io

Source for [jonvillasurdajr.github.io](https://jonvillasurdajr.github.io/), the professional site for Jon Villasurda Jr., MPH.

The Jekyll site presents a consistent professional profile, selected public work, and practical notes on Medicaid, behavioral health, CCBHC implementation, analytics, and program evaluation.

## SEO safeguards

- Unique titles and descriptions, self-referencing canonicals, Open Graph metadata, and crawlable JSON-LD
- A curated sitemap, permissive robots file, and IndexNow verification key
- Deployment-aware health checks that crawl every sitemap URL and validate internal links
- IndexNow submissions generated from the live sitemap after GitHub Pages publishes the current commit
- A daily technical SEO audit with automatic failure/recovery issues
- A daily external-reputation monitor with a primary run and two staggered recovery opportunities that compare Google News and watched publication pages against prior state
- Duplicate-safe recovery gating: later scheduled runs execute only when no earlier scheduled run has completed or remains active that day
- A persistent assigned status issue confirming each completed scan and identifying whether it was a primary, recovery, or manual run
- Prioritized CSV evidence, workflow summaries, and approval-gated correction-request drafts for new reputation findings; actionable issue entries link to prefilled Gmail drafts
- A daily review issue for Search Console, AI visibility, current references, and workflow continuity

The reputation monitor automatically preserves and classifies evidence, but it does not send correction demands or make legal conclusions. Generated outreach text must be checked against the complete article and court record before it is sent.

The primary schedule is 12:23 UTC, with recovery opportunities at 13:53 UTC and 15:23 UTC. GitHub may delay any scheduled event; the recovery gate suppresses duplicate scans after an earlier run succeeds and labels a later scan as a recovery when it is needed. Successful scans update the assigned `Daily reputation monitor status` issue. Findings that need review update `External monitoring review needed`, where each actionable item includes a prefilled Gmail link. The full editable drafts remain available for 30 days in the run artifact as `reputation-watch-drafts.md`.

## Maintenance

GitHub may disable scheduled workflows in a public repository after 60 days without repository activity. Use the monthly review issue to make substantive content updates before that threshold rather than creating placeholder commits.

Run the production audit locally with:

```shell
python scripts/seo_automation.py audit --sitemap https://jonvillasurdajr.github.io/sitemap.xml
```
