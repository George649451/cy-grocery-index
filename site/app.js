(async function () {
  const d = await (await fetch('data.json', { cache: 'no-store' })).json();
  const eur = (v, dp = 2) => v == null ? '—' : '€' + v.toLocaleString('en-GB', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  const fmtDate = s => new Date(s + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  const fmtMonth = m => new Date(m + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
  const el = id => document.getElementById(id);
  const b = d.basket, g = d.generated_from, c = d.catalogue;

  el('mosaic').innerHTML = b.items.slice(0, 24).map((it, i) => `<img src="${it.image}" alt="" loading="eager" decoding="async" style="animation-delay:${(i * 35)}ms" onerror="this.remove()">`).join('');

  el('status').textContent = `Last collection ${fmtDate(g.latest)} · ${c.products.toLocaleString('en-GB')} products tracked · ${g.collection_days} day${g.collection_days === 1 ? '' : 's'} of data since ${fmtDate(g.start)}`;

  // hero
  countUp(el('hero-cost'), b.latest_cost);
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

  // reveal sections as they enter the viewport
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' });
  document.querySelectorAll('.reveal').forEach(n => io.observe(n));

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
