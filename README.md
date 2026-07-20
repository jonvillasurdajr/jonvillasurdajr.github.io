# jonvillasurdajr.github.io

Source for [jonvillasurdajr.github.io](https://jonvillasurdajr.github.io/), the professional site for Jon Villasurda Jr., MPH.

The Jekyll site presents a consistent professional profile, selected public work, and practical notes on Medicaid, behavioral health, CCBHC implementation, analytics, and program evaluation.

## SEO safeguards

- Unique titles and descriptions, self-referencing canonicals, Open Graph metadata, and crawlable JSON-LD
- A curated sitemap, permissive robots file, and IndexNow verification key
- Deployment-aware health checks that crawl every sitemap URL and validate internal links
- IndexNow submissions generated from the live sitemap after GitHub Pages publishes the current commit
- A monthly review issue for Search Console, current references, and workflow continuity

## Maintenance

GitHub may disable scheduled workflows in a public repository after 60 days without repository activity. Use the monthly review issue to make substantive content updates before that threshold rather than creating placeholder commits.

Run the production audit locally with:

```shell
python scripts/seo_automation.py audit --sitemap https://jonvillasurdajr.github.io/sitemap.xml
```
