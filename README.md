# Cyprus Grocery Inflation Tracker

Tracks grocery price inflation in Cyprus by collecting Alphamega's full online
catalogue daily and publishing a properly constructed price index monthly.

Two series:

- **Headline index** — a fixed basket, unit prices (€/kg, €/L), Jevons
  elementary aggregates, weighted with CyStat CPI weights so it is directly
  comparable to the official Food and non-alcoholic beverages index.
- **The real basket** — one household's actual weekly shop (two adults, two
  school-age children), unweighted.

Collected daily, published monthly. Daily grocery inflation is noise.

## Layout

    collector/          daily scrape -> normalised rows, change-log (stdlib only)
    data/catalogue/     product master (no prices)
    data/summary/       daily aggregate counts
    data/basket/        COICOP classes with CyStat weights; basket items
    index/              index computation (recomputable from scratch over all history)
    site/               static site built from index output
    docs/               brief, decisions, methodology

The full price change-log lives in a private companion repo
(`cy-grocery-index-data`); basket-level prices are published here.

## Running the collector locally

    python3 collector/collect.py --data-dir ../cy-grocery-index-data --public-dir data --dry-run

Series start: 12 September 2026.
