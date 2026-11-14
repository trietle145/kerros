// Editor tools (owner: ui): three visual checks, data from insights.py.
//   Citation finder   an evidence constellation: your sentence in the middle, the articles that back it
//                     around it (nearer and bigger = more words in common); select one for its passage and refs.
//   Contradictions    dumbbell rows: the same quantity in two articles, the gap between the numbers.
//   Edit-war radar    a heat map of reverts between named editors (article x year); select an article for a
//                     swim-lane per paragraph, a dot for every time its text was put back.
// Text stays short on purpose: numbers, shapes and one tooltip; the passage itself only on selection.
import { cite, contradictions, find, radar, radarPage } from "/static/api.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
const num = n => Number(n).toLocaleString("en-US");
const day = iso => iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const params = new URLSearchParams(location.search);
const loading = text => `<p class="tool-loading"><i></i>${text}</p>`;
const failed = e => `<p class="alert"><span><b>That did not work.</b> ${esc(e.message)}</span></p>`;
const stems = t => new Set((t.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) || []).map(w => /^\d+$/.test(w) ? w : w.slice(0, 5)));
const marked = (s, keys) => esc(s).replace(/[\p{L}\p{N}]{4,}/gu, w => keys.has(/^\d+$/.test(w) ? w : w.toLowerCase().slice(0, 5)) ? `<mark>${w}</mark>` : w);
// a bare web reference reads as its site and last path part, not a 90-character address
const prettyRef = label => {
  const m = /https?:\/\/([^\s/|]+)([^\s|]*)/.exec(label);
  if (!m) return label;
  const host = m[1].replace(/^www\./, ""), last = decodeURIComponent((m[2].split("?")[0].split("/").filter(Boolean).pop() || "").replace(/\.\w{2,4}$/, "")).replace(/[-_]+/g, " ");
  const rest = label.replace(m[0], "").replace(/\b(Verkkoviite|Osoite)\b/gi, "").replace(/[\s|:=]+/g, " ").trim();
  return rest && !/^\W*$/.test(rest) ? `${host}: ${rest}` : last ? `${host} · ${last}` : host;
};
const clip = (s, n) => s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;

// ---- one tooltip for all three charts ------------------------------------------------------------
const tip = Object.assign(document.createElement("div"), { className: "viz-tip", id: "viz-tip" });
tip.setAttribute("role", "tooltip");
document.body.append(tip);
function showTip(html, x, y) {
  tip.innerHTML = html;
  tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  let left = x + 14, top = y + 16;
  if (left + r.width > innerWidth - 8) left = x - 14 - r.width;
  if (top + r.height > innerHeight - 8) top = y - 16 - r.height;
  tip.style.left = Math.max(8, left) + "px";
  tip.style.top = Math.max(8, top) + "px";
}
const tipAt = (html, el) => { const r = el.getBoundingClientRect(); showTip(html, r.left + r.width / 2, r.bottom); };
const hideTip = () => tip.classList.remove("on");
addEventListener("scroll", hideTip, { passive: true });

// ---- tabs (arrow keys move between them; the address keeps the open tool) ------------------------
const tabs = [...$("tool-tabs").children];
function open(name, focus) {
  hideTip();
  for (const t of tabs) {
    const on = t.dataset.tab === name;
    t.setAttribute("aria-selected", on);
    t.tabIndex = on ? 0 : -1;
    $("panel-" + t.dataset.tab).hidden = !on;
    if (on && focus) t.focus();
  }
  const p = new URLSearchParams(location.search); p.set("tool", name); history.replaceState(null, "", "?" + p);
  if (name === "radar") loadRadar();
  if (name === "cite" && lastCite) drawCite();             // a chart drawn while hidden has no width: redraw now
}
$("tool-tabs").addEventListener("click", e => { const t = e.target.closest("[data-tab]"); if (t) open(t.dataset.tab); });
$("tool-tabs").addEventListener("keydown", e => {
  if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const i = tabs.findIndex(t => t.getAttribute("aria-selected") === "true");
  open(tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length].dataset.tab, true);
});

// copy buttons (reference chips)
document.addEventListener("click", async e => {
  const ex = e.target.closest("[data-example]");
  if (ex) { $("cite-text").value = ex.dataset.example; $("cite-form").requestSubmit(); return; }
  const b = e.target.closest(".ref-chip");
  if (!b) return;
  const label = b.querySelector(".copy-state");
  try { await navigator.clipboard.writeText(b.dataset.copy); label.textContent = "Copied ✓"; }
  catch { label.textContent = "Press Ctrl+C"; }
  b.classList.add("is-copied");
  setTimeout(() => { label.textContent = "Copy"; b.classList.remove("is-copied"); }, 1600);
});

// =====================================================================================================
// 1. Citation finder: the evidence constellation
// =====================================================================================================
let lastCite = null, selected = 0;

$("cite-form").addEventListener("submit", async e => {
  e.preventDefault();
  const text = $("cite-text").value.trim(), out = $("cite-out");
  if (text.length < 8) { out.innerHTML = `<p class="alert"><span><b>Paste a sentence first.</b> A few words at least.</span></p>`; return; }
  out.innerHTML = loading("Searching every current paragraph…");
  try {
    const r = await cite(text);
    lastCite = { text, keys: stems(text), results: r.results.slice(0, 6) };
    selected = 0;
    drawCite(true);
  } catch (err) { out.innerHTML = failed(err); lastCite = null; }
});

function drawCite(animate) {
  const out = $("cite-out"), { text, keys, results } = lastCite;
  hideTip();
  if (!results.length) { out.innerHTML = `<p class="muted-note">No paragraph shares enough words with that sentence.</p>`; return; }
  const W = Math.max(300, Math.min(960, out.clientWidth || 700)), narrow = W < 520, s = narrow ? .72 : 1;   // drawn at its real width: no scaling, so type stays 12-13 px
  const H = narrow ? Math.max(360, W * 1.05) : Math.max(380, Math.min(470, W * .46)), cx = W / 2, cy = H / 2;
  const rx = W / 2 - (narrow ? 58 : 96), ry = H / 2 - (narrow ? 54 : 58), fmin = narrow ? .62 : .5;
  const ovs = results.map(x => x.overlap), hi = Math.max(...ovs), lo = Math.min(...ovs);
  const k = results.length;
  const nodes = results.map((x, i) => {
    const t = hi === lo ? .5 : (x.overlap - lo) / (hi - lo), a = (-90 + i * 360 / k) * Math.PI / 180, f = 1 - (1 - fmin) * t;
    return { x: cx + Math.cos(a) * rx * f, y: cy + Math.sin(a) * ry * f, r: (14 + Math.min(x.overlap, 8) * 2.4) * s, d: x, i };
  });
  const rings = [fmin, (fmin + 1) / 2, 1].map(f => `<ellipse class="ring" cx="${cx}" cy="${cy}" rx="${rx * f}" ry="${ry * f}"/>`).join("");
  const links = nodes.map(n => { const len = Math.hypot(n.x - cx, n.y - cy);
    return `<line class="link" data-i="${n.i}" x1="${cx}" y1="${cy}" x2="${n.x}" y2="${n.y}" style="--len:${len};--i:${n.i};stroke-width:${1.2 + n.d.overlap * .55}"/>`; }).join("");
  const sats = nodes.map(n => `<g class="sat" transform="translate(${n.x} ${n.y})" tabindex="0" role="button" data-i="${n.i}" style="--i:${n.i}"
      aria-label="${esc(n.d.title)}: ${n.d.overlap} shared words, ${n.d.refs.length} references">
      <g class="enter"><g class="body"><circle class="halo" r="${n.r + 7}"/><circle class="node" r="${n.r}"/>
        <text class="count" y="${5 * s}">${n.d.overlap}</text>
        <text class="name" y="${n.r + 17}" lang="fi">${esc(clip(n.d.title, narrow ? 13 : 22))}</text>
        <text class="sub" y="${n.r + 32}">${n.d.refs.length} ref${n.d.refs.length === 1 ? "" : "s"}</text></g></g></g>`).join("");
  out.innerHTML = `<figure class="const${animate ? " is-in" : ""}"><svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="Articles backing your sentence">
      <g class="rings">${rings}</g>${links}
      <g class="core"><circle class="pulse" cx="${cx}" cy="${cy}" r="${44 * s}"/><circle class="center" cx="${cx}" cy="${cy}" r="${36 * s}"/>
        <text class="ctext" x="${cx}" y="${cy - 2}">Your</text><text class="ctext" x="${cx}" y="${cy + 13}">sentence</text></g>${sats}</svg>
      <figcaption>Nearer and bigger = more words in common (the number in each circle). Select one to read it.</figcaption></figure>
    <article class="cite-detail" id="cite-detail" aria-live="polite"></article>`;
  const svg = out.querySelector("svg");
  const pick = i => select(i, false);
  svg.addEventListener("click", e => { const g = e.target.closest(".sat"); if (g) pick(+g.dataset.i); });
  svg.addEventListener("keydown", e => {
    const g = e.target.closest(".sat");
    if (g && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(+g.dataset.i); }
  });
  const hover = (g, x, y, at) => {
    const d = results[+g.dataset.i];
    const html = `<b lang="fi">${esc(d.title)}</b><span class="muted">${esc(d.heading || "Introduction")} · ${d.overlap} shared word${d.overlap === 1 ? "" : "s"}</span>
      <p class="q" lang="fi">${marked(d.sentence, keys)}</p>`;
    at ? tipAt(html, g) : showTip(html, x, y);
  };
  svg.addEventListener("pointermove", e => { const g = e.target.closest(".sat"); g ? hover(g, e.clientX, e.clientY) : hideTip(); });
  svg.addEventListener("pointerleave", hideTip);
  svg.addEventListener("focusin", e => { const g = e.target.closest(".sat"); if (g) hover(g, 0, 0, true); });
  svg.addEventListener("focusout", hideTip);
  select(selected, animate);
  if (animate) out.scrollIntoView({ block: "start", behavior: reduced() ? "auto" : "smooth" });
}

function select(i, first) {
  selected = i;
  const d = lastCite.results[i], box = $("cite-detail");
  for (const g of document.querySelectorAll(".sat")) g.classList.toggle("is-sel", +g.dataset.i === i);
  for (const l of document.querySelectorAll(".link")) l.classList.toggle("is-sel", +l.dataset.i === i);
  box.innerHTML = `<header><h3 lang="fi"><a href="/article/${d.page_id}">${esc(d.title)}</a></h3>
      <span class="pill">${esc(d.heading || "Introduction")}</span><span class="pill num">${d.overlap} shared word${d.overlap === 1 ? "" : "s"}</span>
      <a class="card-link" href="${esc(d.url)}" target="_blank" rel="noopener">This version ↗</a></header>
    <p class="cd-quote" lang="fi">${marked(d.sentence, lastCite.keys)}</p>
    <div class="cd-refs">${d.refs.length ? d.refs.map(r => `<button class="ref-chip" type="button" data-copy="${esc(r.markup)}" title="${esc(r.label)}">
        <span class="ref-label" lang="fi">${esc(clip(prettyRef(r.label), 60))}</span><span class="copy-state">Copy</span></button>`).join("")
      : `<span class="muted-note">No reference sits next to this sentence.</span>`}</div>`;
  if (!first && !reduced()) box.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 220, easing: "cubic-bezier(0.23, 1, 0.32, 1)" });
}
let resizeTimer = 0;
addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (lastCite && !$("panel-cite").hidden) drawCite(false); }, 150); });

// =====================================================================================================
// 2. Contradictions: dumbbell rows
// =====================================================================================================
const HEROES = [[1150, "Suomen sisällissota"], [1256, "Talvisota"], [8295, "Mainilan laukaukset"], [24197, "Jatkosota"]];
let picked = {};
$("contra-quick").innerHTML = `<span class="muted">Try:</span> ` + HEROES.map(([id, t]) => `<button class="chip chip-sm" type="button" data-page="${id}" lang="fi">${esc(t)}</button>`).join("");
let findTimer = 0;
$("contra-q").addEventListener("input", e => {
  clearTimeout(findTimer);
  findTimer = setTimeout(async () => {
    const r = await find(e.target.value).catch(() => ({ articles: [] }));
    picked = Object.fromEntries(r.articles.map(a => [a.title, a.page_id]));
    $("contra-list").innerHTML = r.articles.map(a => `<option value="${esc(a.title)}">`).join("");
  }, 160);
});
$("contra-form").addEventListener("submit", async e => {
  e.preventDefault();
  const title = $("contra-q").value.trim();
  let id = picked[title];
  if (!id && title) id = (await find(title).catch(() => ({ articles: [] }))).articles[0]?.page_id;
  if (id) compare(id); else $("contra-out").innerHTML = `<p class="alert"><span><b>No article by that title.</b> Pick one from the list.</span></p>`;
});
$("contra-quick").addEventListener("click", e => { const b = e.target.closest("[data-page]"); if (b) { $("contra-q").value = b.textContent; compare(+b.dataset.page); } });

// "7 370 punaista" -> {v: 7370, n: "7 370", unit: "punaista"}
const parseFact = f => {
  const m = /^(\d{1,3}(?:[\s  ]\d{3})+|\d+(?:,\d+)?)\s+(.+)$/.exec(f);
  return { v: parseFloat(m[1].replace(/[\s  ]/g, "").replace(",", ".")), n: m[1], unit: m[2] };
};
const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function snippet(text, f) {                                         // ±90 characters around the number, the number marked
  const m = new RegExp(reEsc(f.n) + "\\s+" + reEsc(f.unit)).exec(text);
  if (!m) return esc(clip(text, 180));
  let a = Math.max(0, m.index - 90), b = Math.min(text.length, m.index + m[0].length + 90);
  if (a) a = text.indexOf(" ", a) + 1 || a;
  if (b < text.length) b = text.lastIndexOf(" ", b) > m.index + m[0].length ? text.lastIndexOf(" ", b) : b;
  return (a ? "…" : "") + esc(text.slice(a, m.index)) + `<mark>${esc(m[0])}</mark>` + esc(text.slice(m.index + m[0].length, b)) + (b < text.length ? "…" : "");
}

async function compare(id) {
  const out = $("contra-out");
  out.innerHTML = loading("Comparing each paragraph with its nearest paragraphs elsewhere…");
  const p = new URLSearchParams(location.search); p.set("page", id); history.replaceState(null, "", "?" + p);
  try {
    const r = await contradictions(id);
    const rows = r.pairs.flatMap(c => c.facts.map(f => { const a = parseFact(f.here), b = parseFact(f.there);
      return { c, a, b, gap: Math.abs(a.v - b.v) / Math.max(a.v, b.v) }; })).sort((x, y) => y.gap - x.gap);
    if (!rows.length) { out.innerHTML = `<h2 class="tool-title" lang="fi">${esc(r.title)}</h2><p class="muted-note">No disagreeing numbers found.</p>`; return; }
    const SHOW = 7, row = (x, i) => {
      const max = Math.max(x.a.v, x.b.v) * 1.12, pa = x.a.v / max * 100, pb = x.b.v / max * 100;
      return `<li class="db-row" style="--i:${i}" ${i >= SHOW ? "data-extra hidden" : ""}>
        <button class="db-main" type="button" aria-expanded="false" aria-controls="db-more-${i}">
          <span class="db-label"><b lang="fi">${esc(x.a.unit)}</b><small lang="fi">vs ${esc(clip(x.c.there.title, 26))}</small></span>
          <span class="db-track" aria-hidden="true">
            <i class="db-line" style="left:${Math.min(pa, pb)}%;width:${Math.abs(pa - pb)}%"></i>
            <i class="db-dot here" style="left:${pa}%"></i><i class="db-dot there" style="left:${pb}%"></i>
            <span class="db-val up num" style="left:${pa}%">${num(x.a.v)}</span><span class="db-val down num" style="left:${pb}%">${num(x.b.v)}</span></span>
          <span class="db-gap num">${x.gap < .01 ? "<1" : Math.round(x.gap * 100)}% apart</span></button>
        <div class="db-more" id="db-more-${i}"><div class="db-snips">
          <div><p class="kicker"><i class="key here"></i>This article · ${esc(x.c.here.heading || "Introduction")}</p><p class="snip" lang="fi">${snippet(x.c.here.text, x.a)}</p>
            <a class="card-link" href="${esc(x.c.here.url)}" target="_blank" rel="noopener">This version ↗</a></div>
          <div><p class="kicker"><i class="key there"></i><a href="/article/${x.c.there.page_id}" lang="fi">${esc(x.c.there.title)}</a> · ${esc(x.c.there.heading || "Introduction")}</p>
            <p class="snip" lang="fi">${snippet(x.c.there.text, x.b)}</p>
            <a class="card-link" href="${esc(x.c.there.url)}" target="_blank" rel="noopener">This version ↗</a></div></div></div></li>`;
    };
    out.innerHTML = `<h2 class="tool-title" lang="fi">${esc(r.title)}</h2>
      <p class="viz-sum"><b class="num">${rows.length}</b> number${rows.length === 1 ? "" : "s"} that disagree · largest gap <b class="num">${Math.round(rows[0].gap * 100)}%</b></p>
      <p class="db-legend"><span><i class="key here"></i>This article</span><span><i class="key there"></i>The other article</span><span class="muted">Scales start at zero. Select a row to read both passages.</span></p>
      <ol class="db-list">${rows.map(row).join("")}</ol>
      ${rows.length > SHOW ? `<button class="btn btn-quiet db-all" type="button">Show all ${rows.length}</button>` : ""}`;
    out.querySelector(".tool-title").scrollIntoView({ block: "start", behavior: reduced() ? "auto" : "smooth" });
  } catch (err) { out.innerHTML = failed(err); }
}
$("contra-out").addEventListener("click", e => {
  const main = e.target.closest(".db-main");
  if (main) { const li = main.parentElement, on = !li.classList.contains("is-open"); li.classList.toggle("is-open", on); main.setAttribute("aria-expanded", on); return; }
  if (e.target.closest(".db-all")) {
    const list = $("contra-out").querySelector(".db-list");
    list.querySelectorAll("[data-extra]").forEach((li, j) => { li.hidden = false; li.style.setProperty("--i", j); });
    e.target.closest(".db-all").remove();
  }
});

// =====================================================================================================
// 3. Edit-war radar: heat map and swim-lanes
// =====================================================================================================
let radarLoaded = false, radarData = null;
async function loadRadar() {
  if (radarLoaded) return;
  radarLoaded = true;
  const out = $("radar-out");
  out.innerHTML = loading("Counting reverts…");
  try { radarData = await radar(); drawHeat(); }
  catch (err) { out.innerHTML = failed(err); radarLoaded = false; }
}

function drawHeat(all) {
  const r = radarData, n = r.years.length, SHOW = 14, list = all ? r.articles : r.articles.slice(0, SHOW);
  const top = Math.max(...r.articles.flatMap(a => a.per_year), 1);
  const level = v => v ? Math.sqrt(v / top) : 0;                      // square root: a few hot years must not hide the rest
  const axis = r.years.map((y, i) => y % 5 === 0 ? `<span style="grid-column:${i + 2} / span 4">${y}</span>` : "").join("");
  const rows = list.map((a, ri) => `<button class="heat-row" type="button" data-page="${a.page_id}" style="--r:${ri}"
      aria-label="${esc(a.title)}: ${num(a.named)} reverts between named editors. Open its paragraphs.">
      <span class="heat-name" lang="fi">${esc(a.title)}</span>
      ${a.per_year.map((v, ci) => `<span class="heat-cell" data-y="${r.years[ci]}" data-v="${v}" style="--c:${ci};--v:${level(v).toFixed(3)}"></span>`).join("")}
      <span class="heat-total num">${num(a.named)}</span></button>`).join("");
  $("radar-out").innerHTML = `<div class="heat-legend"><span>Fewer</span><i class="ramp"></i><span>More reverts in a year <b class="num">(up to ${num(top)})</b></span></div>
    <div class="heat" role="group" aria-label="Reverts between named editors, by article and year">
      <div class="heat-grid" style="--n:${n}"><div class="heat-axis" aria-hidden="true"><span></span>${axis}</div>${rows}</div></div>
    ${!all && r.articles.length > SHOW ? `<button class="btn btn-quiet heat-all" type="button">Show all ${r.articles.length}</button>` : ""}
    <details class="table-view"><summary>Show the numbers as a table</summary><div class="tv-scroll"><table><thead><tr><th scope="col">Article</th>${r.years.map(y => `<th scope="col">${String(y).slice(2)}</th>`).join("")}</tr></thead>
      <tbody>${r.articles.map(a => `<tr><th scope="row" lang="fi">${esc(a.title)}</th>${a.per_year.map(v => `<td class="num">${v || ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>
    <aside class="radar-detail" id="radar-detail" hidden></aside>`;
}

const heat = () => $("radar-out");
heat().addEventListener("pointermove", e => {
  const c = e.target.closest(".heat-cell");
  if (!c) return hideTip();
  const row = c.closest(".heat-row"), v = +c.dataset.v;
  showTip(`<b lang="fi">${esc(row.querySelector(".heat-name").textContent)}</b><span class="muted num">${c.dataset.y}: ${v ? v + " revert" + (v === 1 ? "" : "s") + " between named editors" : "none"}</span>`, e.clientX, e.clientY);
});
heat().addEventListener("pointerleave", hideTip);
heat().addEventListener("click", e => {
  if (e.target.closest(".heat-all")) { drawHeat(true); return; }
  const row = e.target.closest(".heat-row");
  if (row) detail(row);
  const tick = e.target.closest(".tick");
  if (tick) hideTip();
});
heat().addEventListener("keydown", e => {                              // arrow keys move between rows
  const row = e.target.closest(".heat-row");
  if (!row || !["ArrowDown", "ArrowUp"].includes(e.key)) return;
  e.preventDefault();
  (e.key === "ArrowDown" ? row.nextElementSibling : row.previousElementSibling)?.focus?.();
});

const T0 = () => Date.parse(radarData.years[0] + "-01-01"), T1 = () => Date.now();
const at = iso => Math.max(0, Math.min(100, (Date.parse(iso) - T0()) / (T1() - T0()) * 100));

async function detail(row) {
  for (const x of heat().querySelectorAll(".heat-row[aria-selected]")) x.removeAttribute("aria-selected");
  row.setAttribute("aria-selected", "true");
  const box = $("radar-detail");
  box.hidden = false;
  box.innerHTML = loading("Reading every version of its paragraphs…");
  box.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
  try {
    const r = await radarPage(+row.dataset.page), years = radarData.years;
    const axis = years.map((y, i) => y % 5 === 0 ? `<span style="left:${at(y + "-01-01")}%">${y}</span>` : "").join("");
    box.innerHTML = `<header><h2 lang="fi">${esc(r.title)}</h2><a class="btn btn-quiet" href="/article/${r.page_id}">Edit timeline</a></header>
      ${!r.paragraphs.length ? `<p class="muted-note">No paragraph was ever put back after being removed.</p>` : `
      <p class="viz-sum">Each lane is a paragraph. A dot is a time its exact text was put back; select one to see that edit on Wikipedia.</p>
      <div class="lanes"><div class="lane-axis" aria-hidden="true">${axis}</div>
      ${r.paragraphs.map((p, i) => {
        const last = p.restores.length ? p.restores.at(-1).at : p.first;
        return `<div class="lane" style="--i:${i}"><p class="lane-head"><b lang="fi">${esc(p.heading || "Introduction")}</b>
            <span class="pill pill-warn num">put back ${num(p.times)}×</span><span class="muted">${p.live ? "still in the article" : "no longer in the article"}</span></p>
          <div class="lane-track"><i class="span" style="left:${at(p.first)}%;width:${p.live ? 100 - at(p.first) : Math.max(1, at(last) - at(p.first))}%"></i>
            ${p.restores.map(x => `<a class="tick" href="${esc(x.diff)}" target="_blank" rel="noopener" style="left:${at(x.at)}%" data-d="${esc(x.at)}"
              aria-label="Put back ${day(x.at)}: see the edit on Wikipedia"></a>`).join("")}</div>
          <p class="lane-text clamp" lang="fi" title="${esc(p.text)}">${esc(p.text)}</p></div>`; }).join("")}</div>`}`;
  } catch (err) { box.innerHTML = failed(err); }
}
$("radar-out").addEventListener("pointerover", e => {
  const t = e.target.closest(".tick");
  if (t) tipAt(`<b>Put back ${day(t.dataset.d)}</b><span class="muted">Select to see the edit</span>`, t);
});
$("radar-out").addEventListener("pointerout", e => { if (e.target.closest(".tick")) hideTip(); });
$("radar-out").addEventListener("focusin", e => { const t = e.target.closest(".tick"); if (t) tipAt(`<b>Put back ${day(t.dataset.d)}</b>`, t); });
$("radar-out").addEventListener("focusout", hideTip);

// ---- start where the address says ----------------------------------------------------------------
open(["cite", "contra", "radar"].includes(params.get("tool")) ? params.get("tool") : "cite");
if (params.get("page")) { open("contra"); compare(+params.get("page")); }
if (params.get("text")) { $("cite-text").value = params.get("text"); $("cite-form").requestSubmit(); }
