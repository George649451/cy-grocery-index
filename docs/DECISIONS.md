# Decisions

Resolved 13 September 2026 before any code was written.

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | Scope | Headline = CPI division 01 (Food and non-alcoholic beverages), plus an alcoholic beverages sub-index. Collector stores the **whole** catalogue. | Food departments have ~90% unit-price coverage; household 38%, homeware 0%. History cannot be backfilled, so collect everything and classify later. |
| 2 | Promotions | Headline uses the **promotional (paid) price**. Shelf-price series and the promotional gap are published alongside. | CyStat counts special-offer prices open to the general public, so this keeps comparability. Loyalty-card-only prices would be excluded by CyStat; whether the API price reflects them is still to be verified. |
| 3 | Real basket | A realistic middle-class basket designed from the catalogue: two adults, two school-age children, ~50-60 lines. | Replaces the earlier 54-line order. |
| 4 | Raw data | Basket-level prices public. Product master (no prices) public. Full 15k-line daily change-log in a **private** repo. | Alphamega's terms contain no clause on scraping or reuse (verified 13 Sep 2026; they are purchase terms only). Residual exposure is the EU database right; publishing an index is a different act from republishing the price list. Not legal advice. |
| 5 | Second retailer | None for v1. | Revisit once the collector has survived a month and classification is done. |

## Facts established on 13 September 2026

- The brief's "205.02 per thousand" is the **HICP** special aggregate for food, alcohol and tobacco (National Accounts weights). The comparable series is the national **CPI**, whose 2026 weights come from the 2023 Household Budget Survey: Food and non-alcoholic beverages 1762 / 10,000 (1906 in 2025); Alcohol and tobacco 528; Furnishings and household 619; Personal care and miscellaneous 572.
- Comparison series: CYSTAT-DB table `0410080E` (CPI by ECOICOP 2, 413 categories, monthly from 2018, base 2025=100), via the PxWeb JSON API at `https://cystatdb.cystat.gov.cy/api/v1/en/8.CYSTAT-DB/Price%20Indices/Consumer%20Price%20Index/`. Class-level weights are referenced to the "CPI Revision January 2026" methodological note; not yet located.
- Unbxd API: page size caps at 100; `search?q=*` reports the whole catalogue (15,214 on 13 Sep) and paginates to the end; the promotion label (Only, Price Drop, Pick Of The Week, ...) is filterable via `filter=promotion:"..."` but not present in product documents.
- Alphamega robots.txt allows all paths with a Cloudflare content signal reserving AI training. The HTML site rejects non-browser clients; the Unbxd API does not.
- Legacy snapshot has 15,207 distinct ids, not the 14,923 stated in the brief.
- Promotion types and `originalPrice`: every **Price Drop** item sampled carries a non-zero `originalPrice`; **Only** and **Mix & Match** items mostly carry `originalPrice: 0`, so for those the pre-promotion shelf price is not recoverable from the API. The shelf-price series therefore understates promotional depth for label-only promotions; the label itself is collected daily so this can be quantified.
- The API accepts `fields=*,promotion` (returns all 65 fields plus the label) and `sort=uniqueId asc`, giving deterministic pagination.

## Scope of the site (13 September 2026)

The site is a general **Cyprus Price Index**, not a grocery-only page. Groceries is module 01; fuel, transport, eating out and utilities are declared as planned modules in `data/modules.csv` and shown on the page with an honest status. Candidate sources: the government [Retail Fuel Price Observatory](https://www.gov.cy/en/service/retail-fuel-price-observatory/) for fuel; regulated bus and taxi tariffs for transport; EAC tariffs and the monthly fuel adjustment for utilities. Eating out has no obvious open source yet. The repository name stays `cy-grocery-index` for now; renaming it would change the Pages URL.

## Module 02: Fuel (13 September 2026)

Source: the Consumer Protection Service's Retail Fuel Price Observatory, an ASP.NET form at `eforms.eservices.cyprus.gov.cy/MCIT/MCIT/PetroleumPrices`, posted per fuel type × district with the page's anti-forgery token. 25 queries a day cover every station (317 on day one; 1,526 station × fuel prices). The server takes ~12 s per query. Station coordinates come from the map links. There is no station id, so stations are keyed by a hash of brand, name, address, area and district.

Published measure: the **national median price per litre** per fuel, daily, with monthly averages as the headline; district medians and brand medians alongside. Median rather than mean because station prices are bounded and skewed by a few outliers. All fuel data is public in this repo: it is government open data, so the private-repo treatment used for the retailer catalogue does not apply.
