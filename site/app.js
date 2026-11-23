(async function () {
  const d = await (await fetch('data.json', { cache: 'no-store' })).json();
  const eur = (v, dp = 2) => v == null ? '—' : '€' + v.toLocaleString('en-GB', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  const fmtDate = s => new Date(s + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  const fmtMonth = m => new Date(m + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  const el = id => document.getElementById(id);
  const b = d.basket, g = d.generated_from, c = d.catalogue;

  el('mosaic').innerHTML = b.items.slice(0, 36).map((it, i) => `<img src="${it.image}" alt="" loading="eager" decoding="async" style="animation-delay:${(i * 20)}ms" onerror="this.remove()">`).join('');

  // coverage row and planned modules
  const fmtShort = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  el('coverage').innerHTML = d.modules.map(m => `<div class="cov"><div class="name">${esc(m.name)}<span class="tag ${m.status}">${m.status}</span></div><div class="src">${m.status === 'live' ? 'Since ' + fmtShort(m.started) + ' · ' : ''}${esc(m.source)}</div></div>`).join('');
  el('coming-list').innerHTML = d.modules.filter(m => m.status === 'planned').map((m, i) => `<div class="row"><span class="name">${esc(m.name)}</span><span class="src">${esc(m.source)}</span><span class="note">${esc(m.note)}</span><span class="st"><span class="tag ${m.status}">${m.status}</span></span></div>`).join('');
  const groc = d.modules.find(m => m.key === 'groceries');
  el('groceries-meta').textContent = `Live since ${fmtShort(groc?.started || g.start)}. ${esc(groc?.note || '')}`;

  el('status').textContent = `Last collection ${fmtDate(g.latest)} · ${c.products.toLocaleString('en-GB')} products tracked · ${g.collection_days} day${g.collection_days === 1 ? '' : 's'} of data since ${fmtDate(g.start)}`;

  // hero
  el('hero-cost').textContent = b.latest_cost.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  el('hero-sub').textContent = `${b.household} · ${b.lines} lines · paid prices on ${fmtDate(g.latest)}`;

  const complete = b.monthly.filter(m => m.complete);
  if (complete.length >= 2) {
    const last = complete[complete.length - 1], prev = complete[complete.length - 2];
    const pct = 100 * (last.cost / prev.cost - 1);
    el('tile-month').textContent = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
    el('tile-month-sub').textContent = `${fmtMonth(last.month)} vs ${fmtMonth(prev.month)}, average weekly cost`;
  } else if (complete.length === 1) {
    el('tile-month').textContent = eur(complete[0].cost);
    el('tile-month-sub').textContent = `${fmtMonth(complete[0].month)} average · first comparison next month`;
  } else {
    const startsMidMonth = g.start.slice(8) !== '01';
    const firstFull = startsMidMonth ? nextMonth(g.start.slice(0, 7)) : g.start.slice(0, 7);
    el('tile-month').textContent = 'From ' + fmtMonth(nextMonth(firstFull)).split(' ')[0];
    el('tile-month-sub').textContent = `${fmtMonth(firstFull)} is the first full month of data; the first month-on-month figure follows in ${fmtMonth(nextMonth(firstFull))}`;
  }
  el('tile-promo').textContent = `${b.on_promo} of ${b.lines}`;
  el('tile-promo-sub').textContent = b.promo_depth_pct != null ? `average ${b.promo_depth_pct}% off where a pre-promotion price is shown` : 'no pre-promotion prices shown';
  el('tile-cat-promo').textContent = c.promo_labelled ? (100 * c.promo_labelled / c.products).toFixed(1) + '%' : '—';
  el('tile-cat-promo-sub').textContent = c.promo_labelled ? `${c.promo_labelled.toLocaleString('en-GB')} of ${c.products.toLocaleString('en-GB')} lines carry a promotion label` : '';

  function nextMonth(m) { const [y, mo] = m.split('-').map(Number); return mo === 12 ? `${y + 1}-01` : `${y}-${String(mo + 1).padStart(2, '0')}`; }

  // chart
  drawChart(el('chart'), b.series);

  // monthly table
  const mt = el('monthly-table').querySelector('tbody');
  b.monthly.forEach((m, i) => {
    const prev = b.monthly[i - 1];
    const chg = prev ? 100 * (m.cost / prev.cost - 1) : null;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${fmtMonth(m.month)}${m.complete ? '' : ' <span class="chip">in progress</span>'}</td><td class="num">${eur(m.cost)}</td><td class="num">${m.index?.toFixed(1) ?? '—'}</td><td class="num ${cls(chg)}">${chg == null ? '—' : (chg >= 0 ? '+' : '') + chg.toFixed(1) + '%'}</td><td>${m.days}</td>`;
    mt.appendChild(tr);
  });

  // groups
  const gmax = Math.max(...b.groups.map(x => x.cost));
  el('groups').innerHTML = b.groups.map(x => `<div class="bar-row"><span class="bar-name">${x.group}</span><div class="bar-track"><div class="bar" style="width:${(100 * x.cost / gmax).toFixed(1)}%"></div></div><span class="bar-val">${eur(x.cost)}</span></div>`).join('');

  // items
  el('items-intro').textContent = `Weekly quantities are fixed; only prices move. A line that is not on sale is marked Imputed: its last price is moved in step with the rest of its group, never frozen. Unit prices are Alphamega's own per-kg / per-litre figures except where marked †, which are derived from the pack size in the product name.`;
  const tb = el('items-table').querySelector('tbody');
  let lastGroup = null;
  b.items.forEach(it => {
    if (it.group !== lastGroup) {
      const gsum = b.groups.find(x => x.group === it.group);
      const tr = document.createElement('tr'); tr.className = 'group';
      tr.innerHTML = `<td colspan="3">${it.group}</td><td class="num">${eur(gsum?.cost)}</td><td colspan="2"></td>`;
      tb.appendChild(tr); lastGroup = it.group;
    }
    const chg = (it.unit_price != null && it.unit_price_start) ? 100 * (it.unit_price / it.unit_price_start - 1) : null;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><div class="item"><img src="${it.image}" alt="" loading="lazy" onerror="this.style.visibility='hidden'"><div><a class="t" href="${it.url}" rel="noopener">${esc(it.title)}</a><span class="note">${esc(it.note)}</span></div></div></td>
      <td class="num">${fmtQty(it.qty)} ${it.basis}</td>
      <td class="num">${eur(it.unit_price)}/${it.basis}${it.unit_price_source === 'title' ? '†' : ''}</td>
      <td class="num">${eur(it.weekly_cost)}</td>
      <td>${it.imputed ? `<span class="chip" title="Not on sale since ${it.last_observed}; price imputed from the movement of its group">Imputed</span>` : it.promotion ? `<span class="chip">${esc(it.promotion)}</span>` : ''}</td>
      <td class="num ${cls(chg)}">${chg == null ? '—' : Math.abs(chg) < 0.05 ? '·' : (chg > 0 ? '▲ ' : '▼ ') + Math.abs(chg).toFixed(1) + '%'}</td>`;
    tb.appendChild(tr);
  });

  // ---------------- utilities module
  if (d.utilities) renderUtilities(d.utilities);
  function renderUtilities(u) {
    const e = u.electricity, eur2 = v => v == null ? '—' : '€' + v.toFixed(2);
    const pctf = (a, b) => (a == null || b == null) ? null : 100 * (a / b - 1);
    const sg = v => v == null ? '—' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1) + '%';
    const cl = v => v == null || Math.abs(v) < 0.05 ? 'flat' : v > 0 ? 'up' : 'down';
    el('util-meta').textContent = `Published tariffs for electricity and water, checked twice a week and logged whenever they change. Last checked ${u.last_checked ? fmtDate(u.last_checked) : '—'}. Bills are for a standard household: ${e ? e.kwh_per_2_months : 700} kWh of electricity every two months and ${u.m3_per_month} m³ of water a month.`;
    const tiles = [];
    if (e && e.months.length) {
      const m = e.months[e.months.length - 1], first = e.months[0], prev = e.months[e.months.length - 2];
      const since = pctf(m.unit_cent_kwh, first.unit_cent_kwh), mom = pctf(m.unit_cent_kwh, prev && prev.unit_cent_kwh);
      tiles.push(`<div class="stat"><p class="label">Electricity · ${fmtMonth(m.month)}</p><p class="value">${m.unit_cent_kwh.toFixed(2)}<span class="delta"> cent/kWh</span></p><p class="sub"><span class="${cl(mom)}">${sg(mom)}</span> on the month before · <span class="${cl(since)}">${sg(since)}</span> since ${fmtMonth(first.month)}</p></div>`);
      tiles.push(`<div class="stat"><p class="label">Electricity · standard bill</p><p class="value">${eur2(m.bill_monthly)}<span class="delta"> /month</span></p><p class="sub">${eur2(m.bill_2_months)} per two-month bill for ${e.kwh_per_2_months} kWh, before VAT</p></div>`);
      el('util-el-p').textContent = `Domestic single-rate tariff (Code ${e.tariff.code}) from the Electricity Authority of Cyprus, in force since ${e.tariff.effective_from ? fmtDate(e.tariff.effective_from) : 'the date first recorded'}: ${e.tariff.energy_cent_kwh.toFixed(2)} cent energy and ${e.tariff.network_cent_kwh.toFixed(2)} cent network per kWh, plus the fuel adjustment EAC publishes each month. Before VAT and levies.`;
      drawMulti(el('util-el-chart'), [{ key: 'unit', label: 'Price per kWh, €', cls: 's1', pts: e.months.map(x => ({ date: x.month + '-01', v: x.unit_cent_kwh / 100 })) }], 'Electricity price per kWh by billing month');
      el('util-el-table').querySelector('tbody').innerHTML = e.months.map((x, i, arr) => {
        const ch = i ? pctf(x.unit_cent_kwh, arr[i - 1].unit_cent_kwh) : null;
        return `<tr><td>${fmtMonth(x.month)}</td><td class="num">${x.fuel_price_eur_mt.toFixed(2)}</td><td class="num">${x.fuel_adjustment_cent.toFixed(2)}</td><td class="num">${x.unit_cent_kwh.toFixed(2)}</td><td class="num ${cl(ch)}">${sg(ch)}</td><td class="num">${eur2(x.bill_monthly)}</td></tr>`;
      }).reverse().join('');
    }
    const withBill = u.water.filter(w => w.bill);
    withBill.forEach(w => tiles.push(`<div class="stat"><p class="label">Water · ${esc(w.district)}</p><p class="value">${eur2(w.bill.monthly)}<span class="delta"> /month</span></p><p class="sub">${u.m3_per_month} m³ a month, before VAT${w.bill.sewerage_monthly != null ? ` · plus ${eur2(w.bill.sewerage_monthly)} sewerage` : ''}</p></div>`));
    el('util-stats').innerHTML = tiles.join('');
    el('util-w-p').textContent = `Domestic tariffs as published by each district organisation. The standard bill is ${u.m3_per_month} m³ a month, fixed charges included, before 5% VAT; sewerage is charged on top. None of these pages states an effective date, so a change is dated by when it is first seen.`;
    const bandTxt = w => (w.flat ? [`first ${w.flat.to} m³ included in the flat charge`] : []).concat(w.bands.reduce((acc, b) => {
      const last = acc[acc.length - 1];
      if (last && last.rate === b.rate) last.to = b.to; else acc.push({ from: b.from, to: b.to, rate: b.rate });
      return acc; }, []).map(b => `${b.to == null ? 'over ' + (b.from - 1) : b.from + '–' + b.to} m³: €${b.rate.toFixed(2)}`)).join(' · ');
    el('util-w-table').querySelector('tbody').innerHTML = u.water.slice().sort((a, b) => (b.bill ? 1 : 0) - (a.bill ? 1 : 0)).map(w => `<tr>
      <td><a class="t" href="${w.source_url}" rel="noopener">${esc(w.district)}${w.area ? ' · ' + esc(w.area) : ''}</a></td>
      <td>${w.bill ? 'every ' + w.bill.period_months + ' months' : 'period not stated'}</td>
      <td class="num">${w.flat ? eur2(w.flat.value) : eur2((w.fixed || 0) + (w.maintenance || 0))}</td>
      <td><span class="note-inline">${bandTxt(w)}</span></td>
      <td class="num">${w.bill && w.bill.sewerage_per_m3 != null ? eur2(w.bill.sewerage_per_m3) : '—'}</td>
      <td class="num">${w.bill ? eur2(w.bill.monthly) : '<span class="flat">not computed</span>'}</td></tr>`).join('');
  }

  // ---------------- fuel module
  if (d.fuel) renderFuel(d.fuel);
  function renderFuel(f) {
    const L = f.names, order = f.order;
    const eurL = v => v == null ? '—' : '€' + v.toFixed(3);
    const dv = (v, ref) => v == null ? '—' : (v - ref >= 0 ? '+' : '−') + Math.abs(v - ref).toFixed(3);
    const fc = v => v == null || Math.abs(v) < 0.0005 ? 'flat' : v > 0 ? 'up' : 'down';
    const fm = d.modules.find(m => m.key === 'fuel') || {};
    const e = f.ec;
    const pct = (now, then) => (now == null || then == null) ? null : 100 * (now / then - 1);
    const sgn = v => v == null ? '—' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1) + '%';
    if (e) {
      el('fuel-meta').textContent = `National average prices from the European Commission's Weekly Oil Bulletin, ${e.weeks.toLocaleString('en-GB')} weeks back to ${new Date(e.first_week + 'T00:00:00').getFullYear()}. Latest week: ${fmtDate(e.latest.date)}. Per-station prices were collected daily from ${fmtShort(f.start)} to ${fmtShort(f.latest)}, until the government observatory moved behind a CAPTCHA; on the ${e.overlap.mondays} Mondays both sources cover, they agree to within ${(e.overlap.mean_abs_diff_u95 * 100).toFixed(1)} cent on average.`;
      const tiles = [['unleaded95', L.unleaded95], ['diesel', L.diesel], ['heating_oil', L.heating_oil]];
      el('fuel-stats').innerHTML = tiles.map(([k, name]) => {
        const wk = pct(e.latest[k], e.prev_week && e.prev_week[k]), yr = pct(e.latest[k], e.year_ago && e.year_ago[k]);
        return `<div class="stat"><p class="label">${name} · week of ${fmtShort(e.latest.date)}</p><p class="value">${eurL(e.latest[k])}<span class="delta"> /L</span></p><p class="sub"><span class="${fc(wk)}">${sgn(wk)}</span> on the week before · <span class="${fc(yr)}">${sgn(yr)}</span> on a year ago</p></div>`;
      }).join('') + `<div class="stat"><p class="label">Diesel premium over unleaded 95</p><p class="value">${(e.latest.diesel - e.latest.unleaded95).toFixed(3)}<span class="delta"> €/L</span></p><p class="sub">a year ago it was ${e.year_ago ? (e.year_ago.diesel - e.year_ago.unleaded95).toFixed(3) : '—'} €/L</p></div>`;
      const yearSeries = e.series.slice(-53);
      drawMulti(el('fuel-chart'), [
        { key: 'unleaded95', label: L.unleaded95, cls: 's1', pts: yearSeries.filter(p => p.unleaded95 != null).map(p => ({ date: p.date, v: p.unleaded95 })) },
        { key: 'diesel', label: L.diesel, cls: 's2', pts: yearSeries.filter(p => p.diesel != null).map(p => ({ date: p.date, v: p.diesel })) },
      ]);
      el('fuel-monthly').querySelector('tbody').innerHTML = e.monthly.slice(-13).map((m, i, arr) => {
        const prev = arr[i - 1]; const ch = prev ? pct(m.unleaded95, prev.unleaded95) : null;
        return `<tr><td>${fmtMonth(m.month)}${m.complete ? '' : ' <span class="chip">in progress</span>'}</td><td class="num">${eurL(m.unleaded95)}</td><td class="num">${eurL(m.diesel)}</td><td class="num">${eurL(m.heating_oil)}</td><td class="num ${fc(ch)}">${sgn(ch)}</td><td class="num">${m.weeks}</td></tr>`;
      }).reverse().join('');
      el('fuel-district-p').textContent = `Station snapshot from ${fmtDate(f.latest)}, the last day per-station prices could be collected. Median price, with the cheapest and dearest station in each district.`;
      el('fuel-brand-p').textContent = `Station snapshot from ${fmtDate(f.latest)}. Median across each brand's stations. Brands with fewer than three stations are left out.`;
    }
    // districts
    el('fuel-districts').querySelector('tbody').innerHTML = f.districts.map(r => {
      const c = k => r[k] ? `${eurL(r[k].median)}<span class="delta"> ${eurL(r[k].min).replace('€','')}–${eurL(r[k].max).replace('€','')}</span>` : '—';
      return `<tr><td>${esc(r.district)}</td><td class="num">${r.unleaded95 ? r.unleaded95.n : '—'}</td>${['unleaded95','diesel','unleaded98','heating_oil'].map(k => `<td class="num">${c(k)}</td>`).join('')}</tr>`;
    }).join('');
    // brands
    const n95 = f.national.unleaded95.median, nd = f.national.diesel.median;
    el('fuel-brands').querySelector('tbody').innerHTML = f.brands.map(b => `<tr><td>${esc(b.brand)}</td><td class="num">${b.n}</td><td class="num">${eurL(b.unleaded95)}</td><td class="num ${fc(b.unleaded95 - n95)}">${dv(b.unleaded95, n95)}</td><td class="num">${eurL(b.diesel)}</td><td class="num ${fc(b.diesel == null ? null : b.diesel - nd)}">${dv(b.diesel, nd)}</td></tr>`).join('');
  }

  function drawMulti(host, seriesList, aria) {
    const W = 1000, H = 340, m = { t: 24, r: 110, b: 36, l: 56 };
    const all = seriesList.flatMap(s => s.pts);
    const xs = all.map(p => new Date(p.date + 'T00:00:00').getTime());
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (x1 - x0 < 6 * 864e5) x1 = x0 + 30 * 864e5;
    let ymin = Math.min(...all.map(p => p.v)), ymax = Math.max(...all.map(p => p.v));
    const pad = Math.max((ymax - ymin) * 0.15, 0.02);
    ymin = Math.floor((ymin - pad) * 20) / 20; ymax = Math.ceil((ymax + pad) * 20) / 20;
    const X = t => m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r);
    const Y = v => m.t + (1 - (v - ymin) / (ymax - ymin)) * (H - m.t - m.b);
    const step = (ymax - ymin) / 4;
    const yt = []; for (let v = ymin; v <= ymax + 1e-9; v += step) yt.push(v);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${aria || 'National average fuel price per litre over time'}">`;
    svg += yt.map(v => `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">€${v.toFixed(2)}</text>`).join('');
    const mt = []; const d0 = new Date(x0); d0.setDate(1); for (let dd = new Date(d0); dd.getTime() <= x1; dd.setMonth(dd.getMonth() + 1)) if (dd.getTime() >= x0 + 3 * 864e5) mt.push(dd.getTime());
    svg += mt.map(t => `<text class="axis" x="${X(t)}" y="${H - 12}" text-anchor="middle">${new Date(t).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })}</text>`).join('');
    if (!mt.length || X(mt[0]) - X(x0) > 70) svg += `<text class="axis" x="${X(x0)}" y="${H - 12}" text-anchor="start">${new Date(x0).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</text>`;
    seriesList.forEach(s => {
      const T = s.pts.map(p => new Date(p.date + 'T00:00:00').getTime());
      const path = s.pts.map((p, i) => `${i ? 'L' : 'M'}${X(T[i]).toFixed(1)},${Y(p.v).toFixed(1)}`).join(' ');
      svg += `<path class="line ${s.cls}" d="${path}"/>`;
      if (s.pts.length <= 62) svg += s.pts.map((p, i) => `<circle class="dot ${s.cls}" r="4" cx="${X(T[i])}" cy="${Y(p.v)}"/>`).join('');
      const last = s.pts[s.pts.length - 1];
      svg += `<text class="endlabel" x="${X(T[T.length - 1]) + 10}" y="${Y(last.v) + 4}">€${last.v.toFixed(3)}</text>`;
    });
    svg += `<line class="crosshair" x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" style="display:none"/><rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}"/></svg>`;
    svg += `<div class="legend">${seriesList.map(s => `<span class="${s.cls}">${esc(s.label)}</span>`).join('')}</div><div class="tooltip"></div>`;
    host.innerHTML = svg;
    const svgEl = host.querySelector('svg'), tip = host.querySelector('.tooltip'), xh = host.querySelector('.crosshair');
    const dates = [...new Set(all.map(p => p.date))].sort(); const DT = dates.map(dd => new Date(dd + 'T00:00:00').getTime());
    svgEl.addEventListener('mousemove', ev => {
      const r = svgEl.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * W;
      let best = 0, bd = Infinity; DT.forEach((t, i) => { const q = Math.abs(X(t) - px); if (q < bd) { bd = q; best = i; } });
      xh.setAttribute('x1', X(DT[best])); xh.setAttribute('x2', X(DT[best])); xh.style.display = '';
      const vals = seriesList.map(s => { const p = s.pts.find(q => q.date === dates[best]); return p ? `${s.label} €${p.v.toFixed(3)}` : null; }).filter(Boolean).join(' · ');
      tip.style.display = 'block'; tip.style.left = (X(DT[best]) / W * r.width) + 'px'; tip.style.top = (m.t / H * r.height + 14) + 'px';
      tip.textContent = `${fmtDate(dates[best])} · ${vals}`;
    });
    svgEl.addEventListener('mouseleave', () => { tip.style.display = 'none'; xh.style.display = 'none'; });
  }

  function countUp(node, target) {
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const fmt = v => v.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (reduce) { node.textContent = fmt(target); return; }
    const t0 = performance.now(), dur = 1100, from = target * 0.9;
    (function step(t) { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); node.textContent = fmt(from + (target - from) * e); if (k < 1) requestAnimationFrame(step); })(t0);
  }
  function cls(v) { return v == null || Math.abs(v) < 0.05 ? 'flat' : v > 0 ? 'up' : 'down'; }
  function fmtQty(q) { return Number.isInteger(q) ? q : q.toLocaleString('en-GB', { maximumFractionDigits: 3 }); }
  function esc(s) { return String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch])); }

  function drawChart(host, series) {
    const W = 1000, H = 340, m = { t: 24, r: 90, b: 36, l: 56 };
    const xs = series.map(s => new Date(s.date + 'T00:00:00').getTime());
    const ys = series.map(s => s.cost);
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (x1 - x0 < 6 * 864e5) x1 = x0 + 30 * 864e5;            // at least a month of horizon while the series is young
    let ymin = Math.min(...ys), ymax = Math.max(...ys);
    const pad = Math.max((ymax - ymin) * 0.25, ymax * 0.03);
    ymin = Math.floor((ymin - pad) / 5) * 5; ymax = Math.ceil((ymax + pad) / 5) * 5;
    const X = t => m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r);
    const Y = v => m.t + (1 - (v - ymin) / (ymax - ymin)) * (H - m.t - m.b);
    const yticks = []; const step = niceStep((ymax - ymin) / 4);
    for (let v = ymin; v <= ymax + 1e-9; v += step) yticks.push(+v.toFixed(2));
    const xt = monthTicks(x0, x1);
    const path = series.map((s, i) => `${i ? 'L' : 'M'}${X(xs[i]).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join(' ');
    const showDots = series.length <= 62;
    const last = series[series.length - 1];
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly basket cost over time">`;
    svg += yticks.map(v => `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">€${v}</text>`).join('');
    svg += xt.map(t => `<text class="axis" x="${X(t)}" y="${H - 12}" text-anchor="middle">${new Date(t).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })}</text>`).join('');
    if (!xt.length || xt[0] - x0 > 3 * 864e5) svg += `<text class="axis" x="${X(x0)}" y="${H - 12}" text-anchor="start">${new Date(x0).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</text>`;
    const area = path + ` L${X(xs[xs.length - 1]).toFixed(1)},${(H - m.b).toFixed(1)} L${X(xs[0]).toFixed(1)},${(H - m.b).toFixed(1)} Z`;
    svg += `<defs><linearGradient id="areaFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#2a78d6" stop-opacity=".22"/><stop offset="1" stop-color="#2a78d6" stop-opacity="0"/></linearGradient></defs>`;
    if (series.length >= 3) svg += `<path class="area" d="${area}"/>`;
    svg += `<path class="line" d="${path}"/>`;
    if (showDots) svg += series.map((s, i) => `<circle class="dot" r="4" cx="${X(xs[i])}" cy="${Y(ys[i])}"/>`).join('');
    svg += `<text class="endlabel" x="${X(xs[xs.length - 1]) + 10}" y="${Y(last.cost) + 4}">${eur(last.cost)}</text>`;
    svg += `<line class="crosshair" id="xh" x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" style="display:none"/>`;
    svg += `<rect class="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}"/></svg><div class="tooltip" id="tip"></div>`;
    host.innerHTML = svg;
    const svgEl = host.querySelector('svg'), tip = host.querySelector('#tip'), xh = host.querySelector('#xh');
    svgEl.addEventListener('mousemove', ev => {
      const r = svgEl.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * W;
      let best = 0, bd = Infinity; xs.forEach((t, i) => { const dd = Math.abs(X(t) - px); if (dd < bd) { bd = dd; best = i; } });
      xh.setAttribute('x1', X(xs[best])); xh.setAttribute('x2', X(xs[best])); xh.style.display = '';
      tip.style.display = 'block'; tip.style.left = (X(xs[best]) / W * r.width) + 'px'; tip.style.top = (Y(ys[best]) / H * r.height - 10) + 'px';
      tip.textContent = `${fmtDate(series[best].date)} · ${eur(ys[best])} · ${series[best].priced}/${b.lines} priced`;
    });
    svgEl.addEventListener('mouseleave', () => { tip.style.display = 'none'; xh.style.display = 'none'; });
    function niceStep(raw) { const p = Math.pow(10, Math.floor(Math.log10(raw))); const f = raw / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
    function monthTicks(a, z) { const out = []; const d0 = new Date(a); d0.setDate(1); for (let d = new Date(d0); d.getTime() <= z; d.setMonth(d.getMonth() + 1)) if (d.getTime() >= a + 864e5 * 3) out.push(d.getTime()); return out; }
  }
})().catch(e => { document.getElementById('status').textContent = 'Could not load data: ' + e.message; });
