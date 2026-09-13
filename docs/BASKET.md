# The real basket

One household's weekly shop: two adults and two school-age children, shopping
at Alphamega. Sixty lines in `data/basket/real_basket.csv`, entered on
12 September 2026 and fixed for twelve months.

Each line carries a **weekly quantity in kg, litres or pieces**, not a number
of packs. The weekly cost is the sum of unit price × quantity, so a pack that
shrinks at an unchanged shelf price shows up as inflation, as it should.

Unit prices come from the API's `comparisonPrice`. Four lines have none
(sugar, bananas, toilet rolls, kitchen rolls); for those the pack size is
hand-assigned from the product title and recorded in `hand_pack_size`, with
`unit_price_source = title`.

Selection rules: mainstream mid-market lines, a mix of own-brand and national
brands, stocked at all three branches on 13 September 2026, unit-priced by
weight or volume wherever the category allows. Seasonal produce (grapes,
melon) was excluded in favour of year-round lines.

Weekly cost at 13 September 2026 prices: **€208.79** (promotional prices).

Churn: a delisted line is imputed from its group's average movement and
replaced at the next re-base. Nothing enters or leaves mid-year.
