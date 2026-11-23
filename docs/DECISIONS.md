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

## Fuel reliability (12 October 2026)

In the first 30 days the observatory was unreachable at collection time on 7 days (timeouts, or a form page without the anti-forgery token). Those days are gaps; prices cannot be backfilled. Mitigation: the fuel workflow now runs three times a day and the collector exits immediately once the day has a successful run, so extra attempts cost nothing. Failures are now recorded in `data/fuel/runs.csv` with an `error` column instead of only as a red workflow.

## Status review (19 November 2026)

- **Fuel paused.** On 30 October 2026 the Retail Fuel Price Observatory moved from the eforms portal to `petroleumprices.meci.gov.cy`. The new search form requires a CAPTCHA on every query. That is a clear signal that automated collection is not wanted, and it is not circumvented here. The fuel series stops at 29 October (40 collected days). The scheduled workflow is removed, the module is shown as *Paused* on the site, and the collected data stays published. Restart only with a source that permits automated access.
- **Imputation implemented for the real basket.** A basket line with no price on a day is no longer carried forward at its last price. Its last observed unit price is moved by the Jevons movement of the other lines in its group over the same interval (whole basket as fallback). Imputed lines are marked in the item table.
- **Source-error guard.** On 20 October 2026 Alphamega listed a 1.5 L cola at an unchanged €1.95 with a unit price of 13/L instead of 1.30/L, for one day. An observation whose implied pack size (price ÷ unit price) halves or doubles overnight is now set aside and the line imputed for that day, unless the new size persists for two further observations, in which case it is a real pack change. Set-aside observations are listed under `anomalies` in the site data. Without the guard October read +4.5% on September; with it, +4.0%.
- **Grocery gap on 4 November.** The catalogue was collected but GitHub returned a 500 on the push to the private repo and the day was lost. Both pushes in the workflow now retry five times.

## Fuel restarts on a weekly official source (19 November 2026)

Module 02 now runs on the European Commission's **Weekly Oil Bulletin**: the consumer price with taxes in force each Monday, national average, for unleaded 95, diesel and heating oil, with history from January 2005. It is a plain workbook download, collected by `collector/fuel_ec.py` three times a week and rewritten in full each run so revisions are picked up.

What is lost: daily frequency, districts, brands and the station-level spread. What is gained: 21 years of history and year-on-year comparisons from day one. On the seven Mondays where both exist, the Commission's unleaded 95 figure and the mean of our own station prices differ by 0.2 cent on average, so the weekly series is a faithful continuation of the same underlying data. The station data for 13 September to 29 October 2026 stays published as a dated snapshot.

Route back to station-level data: data.gov.cy lists a "Retail Fuel Price Observatory (API)" dataset offering an XML feed on application to the Consumer Protection Service, on condition that the applicant offers consumers a free version of the observatory. The listing predates the October 2026 migration and has not been verified as still operating. Applying is the owner's decision.

## Module 03: Utilities (23 November 2026)

A register of published tariffs, checked twice a week by `collector/utilities.py`, with every change logged in `data/utilities/changes.csv`.

**Electricity.** EAC domestic single-rate tariff, Code 01. Price per kWh = energy charge + network charge + ancillary services charge + the *revised* fuel adjustment EAC publishes each month for low-voltage, bi-monthly consumers, which is the figure EAC says it bills. The series starts in May 2026, when the current tariff and its €600 per tonne base fuel price took effect; earlier 2026 months were adjusted from a €300 base under a tariff this project never recorded, so they are stored but not turned into a price. Standard bill: 700 kWh per two months plus the meter and supply charges. Excluded: VAT, the public service obligation charge and the renewables levy.

**Water.** Domestic tariffs for Limassol (billed every four months) and Larnaca (every three). Standard bill: 15 m³ a month, fixed and maintenance charges included, before 5% VAT; sewerage shown separately. Famagusta (Paralimni) is recorded but no bill is computed because the page does not state the billing period. Paphos publishes no prices and no tariff page was found for Nicosia. The pages carry no effective dates, so a change is dated by when it is first seen.

The standard household (700 kWh per two months, 15 m³ of water a month) is an assumption of this project, set in `index/build_site.py`.

## Module 04: Eating out (23 November 2026)

A fixed list of 45 menu items at nine Limassol restaurants, in `data/eating_out/items.csv`: two Cypriot tavernas, a bistro, a Syrian restaurant, a seafood chain, a souvlaki house and three coffee places. Each row carries the menu URL and a pattern that locates the item and its price in the page's visible text. `collector/eating_out.py` reads them every Monday.

**Sources.** Only menus published on a restaurant's own website. Delivery platforms and review sites are not used: their terms rule them out and their prices include platform mark-ups. About forty Limassol restaurants were checked on 23 November 2026; most traditional places publish no priced menu of their own, which is why the list is short on them. PDF-only menus (Neon Phaliron, Pyxida) and menus hosted by third parties (Dionysus Mansion, Pier One) are left out for now.

**Measure.** The menu price index is the geometric mean of price relatives since the first check, over items priced on both dates, so an item that leaves a menu is treated as moving with the rest. A price that more than doubles or halves between checks is set aside as a parsing slip and listed in `anomalies.csv`. The list is fixed for twelve months. The typical prices shown beside the index (meze per person, taverna main course, a coffee) are medians of the current menu prices and are descriptive only.

**Known weaknesses.** Limassol only. Nine restaurants is a small sample and it is not random: it is the set that publishes prices. Karatello and Artima share an operator. The Syrian Restaurant's site may be out of date. Ownership of the Sterna site was not confirmed. Two chains publish Cyprus-wide prices.
