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
  el('coming-list').innerHTML = d.modules.filter(m => m.status !== 'live').map((m, i) => `<div class="row"><span class="name">${esc(m.name)}</span><span class="src">${esc(m.source)}</span><span class="note">${esc(m.note)}</span><span class="st"><span class="tag ${m.status}">${m.status}</span></span></div>`).join('');
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
  el('items-intro').textContent = `Weekly quantities are fixed; only prices move. Unit prices are Alphamega's own per-kg / per-litre figures except where marked †, which are derived from the pack size in the product name.`;
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
      <td>${it.promotion ? `<span class="chip">${esc(it.promotion)}</span>` : ''}</td>
      <td class="num ${cls(chg)}">${chg == null ? '—' : Math.abs(chg) < 0.05 ? '·' : (chg > 0 ? '▲ ' : '▼ ') + Math.abs(chg).toFixed(1) + '%'}</td>`;
    tb.appendChild(tr);
  });

  // ---------------- fuel module
  if (d.fuel) renderFuel(d.fuel);
  function renderFuel(f) {
    const L = f.names, order = f.order;
    const eurL = v => v == null ? '—' : '€' + v.toFixed(3);
    el('fuel-meta').textContent = `Live since ${fmtDate(f.start)}. ${f.stations} stations reporting to the government observatory; every station, every day.`;
    const main = ['unleaded95', 'diesel', 'heating_oil'];
    el('fuel-stats').innerHTML = main.map(k => { const n = f.national[k]; if (!n) return ''; return `<div class="stat"><p class="label">${L[k]} · national median</p><p class="value">${eurL(n.median)}<span class="delta"> /L</span></p><p class="sub">${n.n} stations · cheapest ${eurL(n.min)} · dearest ${eurL(n.max)}</p></div>`; }).join('')
      + `<div class="stat"><p class="label">Spread · unleaded 95</p><p class="value">${eurL(f.national.unleaded95.max - f.national.unleaded95.min).replace('€','')}<span class="delta"> €/L</span></p><p class="sub">between the dearest and cheapest station in Cyprus today</p></div>`;
    drawMulti(el('fuel-chart'), [
      { key: 'unleaded95', label: L.unleaded95, cls: 's1', pts: f.series.unleaded95.map(p => ({ date: p.date, v: p.median })) },
      { key: 'diesel', label: L.diesel, cls: 's2', pts: f.series.diesel.map(p => ({ date: p.date, v: p.median })) },
    ]);
    // monthly table
    const months = [...new Set(order.flatMap(k => f.monthly[k].map(m => m.month)))].sort();
    el('fuel-monthly').querySelector('tbody').innerHTML = months.map(m => {
      const cell = k => { const r = f.monthly[k].find(x => x.month === m); return r ? eurL(r.median) : '—'; };
      const days = (f.monthly.unleaded95.find(x => x.month === m) || {}).days ?? '';
      const complete = (f.monthly.unleaded95.find(x => x.month === m) || {}).complete;
      return `<tr><td>${fmtMonth(m)}${complete ? '' : ' <span class="chip">in progress</span>'}</td>${['unleaded95','diesel','unleaded98','heating_oil','kerosene'].map(k => `<td class="num">${cell(k)}</td>`).join('')}<td class="num">${days}</td></tr>`;
    }).join('');
    // districts
    el('fuel-districts').querySelector('tbody').innerHTML = f.districts.map(r => {
      const c = k => r[k] ? `${eurL(r[k].median)}<span class="delta"> ${eurL(r[k].min).replace('€','')}–${eurL(r[k].max).replace('€','')}</span>` : '—';
      return `<tr><td>${esc(r.district)}</td><td class="num">${r.unleaded95 ? r.unleaded95.n : '—'}</td>${['unleaded95','diesel','unleaded98','heating_oil'].map(k => `<td class="num">${c(k)}</td>`).join('')}</tr>`;
    }).join('');
    // brands
    const n95 = f.national.unleaded95.median, nd = f.national.diesel.median;
    const dv = (v, ref) => v == null ? '—' : (v - ref >= 0 ? '+' : '−') + Math.abs(v - ref).toFixed(3);
    const fc = v => v == null || Math.abs(v) < 0.0005 ? 'flat' : v > 0 ? 'up' : 'down';
    el('fuel-brands').querySelector('tbody').innerHTML = f.brands.map(b => `<tr><td>${esc(b.brand)}</td><td class="num">${b.n}</td><td class="num">${eurL(b.unleaded95)}</td><td class="num ${fc(b.unleaded95 - n95)}">${dv(b.unleaded95, n95)}</td><td class="num">${eurL(b.diesel)}</td><td class="num ${fc(b.diesel == null ? null : b.diesel - nd)}">${dv(b.diesel, nd)}</td></tr>`).join('');
  }

  function drawMulti(host, seriesList) {
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
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="National median fuel price per litre over time">`;
    svg += yt.map(v => `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis" x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">€${v.toFixed(2)}</text>`).join('');
    const mt = []; const d0 = new Date(x0); d0.setDate(1); for (let dd = new Date(d0); dd.getTime() <= x1; dd.setMonth(dd.getMonth() + 1)) if (dd.getTime() >= x0 + 3 * 864e5) mt.push(dd.getTime());
    svg += mt.map(t => `<text class="axis" x="${X(t)}" y="${H - 12}" text-anchor="middle">${new Date(t).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })}</text>`).join('');
    if (!mt.length || mt[0] - x0 > 3 * 864e5) svg += `<text class="axis" x="${X(x0)}" y="${H - 12}" text-anchor="start">${new Date(x0).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</text>`;
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
