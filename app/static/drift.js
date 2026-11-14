// Language drift (owner: ui): which words Finnish Wikipedia used for a topic, year by year, from
// app/static/drift.json (tools/make_drift.py). Line chart in plain SVG: one axis, 2px lines, direct
// labels at the line ends plus a legend, a crosshair tooltip on hover and on arrow keys, a table view.
// Series colours: the dataviz reference palette's dark steps, validated against --surface.
import { drift } from "/static/api.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
const num = n => Number(n).toLocaleString("en-US");
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5"];      // fixed order, never cycled
const MIN_TOTAL = 10;                                         // years with fewer mentions are too thin to show a share

let data, topic, mode = "share", hover = null, drawn = null;

const params = new URLSearchParams(location.search);
drift().then(d => {
  data = d;
  $("topics").innerHTML = d.topics.map((t, i) => `<button type="button" role="tab" id="tab-${t.id}" aria-controls="drift"
     aria-selected="${i === 0}" data-id="${t.id}">${esc(t.title)}</button>`).join("");
  select(d.topics.find(t => t.id === params.get("topic")) || d.topics[0], false);
}).catch(e => { $("drift").innerHTML = `<p class="alert"><span><b>Could not load the data.</b> ${esc(e.message)}</span></p>`; });

function select(t, animate = true) {
  topic = t;
  for (const b of $("topics").children) b.setAttribute("aria-selected", b.dataset.id === t.id);
  $("d-title").textContent = t.title;
  $("d-note").innerHTML = esc(t.note) + (t.id === "1918"     // the debate is notable enough to have its own article
    ? ` <a href="/article/250972" lang="fi">Suomen sisällissodan nimet</a> covers the names themselves.` : "");
  history.replaceState(null, "", "?topic=" + t.id + (params.get("mock") ? "&mock=" + params.get("mock") : ""));
  draw(animate);
  table();
  flips();
}

$("topics").addEventListener("click", e => { const b = e.target.closest("[data-id]"); if (b) select(data.topics.find(t => t.id === b.dataset.id)); });
$("topics").addEventListener("keydown", e => {                  // tabs: arrow keys move between topics
  if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const tabs = [...$("topics").children], i = tabs.findIndex(b => b.getAttribute("aria-selected") === "true");
  const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
  next.focus(); next.click();
});
$("d-mode").addEventListener("click", e => {
  const b = e.target.closest("[data-mode]");
  if (!b || b.dataset.mode === mode) return;
  mode = b.dataset.mode;
  for (const x of $("d-mode").children) x.setAttribute("aria-checked", x.dataset.mode === mode);
  draw(false);
});

const totals = () => data.years.map((_, i) => topic.terms.reduce((a, t) => a + t.counts[i], 0));
function values() {
  const tot = totals();
  const from = mode === "share" ? Math.max(0, tot.findIndex(x => x >= MIN_TOTAL)) : Math.max(0, tot.findIndex(x => x > 0));
  return { from, tot, series: topic.terms.map(t => t.counts.map((c, i) => mode === "share" ? (tot[i] ? c / tot[i] : 0) : c)) };
}
const fmt = v => mode === "share" ? `${Math.round(v * 100)}%` : num(v);
function niceMax(m) { const p = 10 ** Math.floor(Math.log10(m || 1)); return Math.ceil(m / p / (m / p > 5 ? 2 : 1)) * p * (m / p > 5 ? 2 : 1); }

function draw(animate) {
  const svg = $("d-svg"), W = svg.parentElement.clientWidth, H = Math.max(240, Math.min(340, W * 0.45));
  const narrow = W < 560, M = { l: 44, r: narrow ? 12 : 128, t: 14, b: 28 };
  const { from, series } = values(), years = data.years.slice(from), n = years.length;
  const max = mode === "share" ? 1 : niceMax(Math.max(...series.flat()));
  const x = i => M.l + (n === 1 ? 0 : (i - from) / (n - 1)) * (W - M.l - M.r);
  const y = v => M.t + (1 - v / max) * (H - M.t - M.b);
  const ticks = mode === "share" ? [0, .25, .5, .75, 1] : [0, max / 4, max / 2, max * 3 / 4, max];
  const color = k => `var(${SERIES[k]})`;
  const paths = series.map((s, k) => `<path class="line" d="${s.slice(from).map((v, j) => `${j ? "L" : "M"}${x(from + j).toFixed(1)},${y(v).toFixed(1)}`).join("")}"
      style="stroke:${color(k)}" pathLength="1"/>`).join("");
  // direct labels at the line ends, pushed apart so they never overlap (text in text colour, a dot carries the hue)
  let labels = series.map((s, k) => ({ k, y: y(s[s.length - 1]) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + 15);
  const over = labels.length ? labels[labels.length - 1].y - (H - M.b + 4) : 0;
  if (over > 0) labels = labels.map(l => ({ ...l, y: l.y - over }));
  const ends = narrow ? "" : labels.map(l => `<g class="end"><circle cx="${W - M.r + 10}" cy="${l.y}" r="3.5" style="fill:${color(l.k)}"/>
      <text x="${W - M.r + 18}" y="${l.y + 4}">${esc(topic.terms[l.k].term)}</text></g>`).join("");
  const step = Math.ceil(n / (narrow ? 5 : 9));
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  svg.innerHTML = `<g class="grid">${ticks.map(t => `<line x1="${M.l}" x2="${W - M.r}" y1="${y(t)}" y2="${y(t)}"/>
      <text x="${M.l - 8}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`).join("")}</g>
    <g class="xaxis">${years.map((yr, j) => j % step && j !== n - 1 ? "" : `<text x="${x(from + j)}" y="${H - 8}" text-anchor="middle">${yr}</text>`).join("")}</g>
    <g class="lines">${paths}</g>${ends}
    <g class="cross" id="d-cross" style="display:none"><line y1="${M.t}" y2="${H - M.b}"/>${series.map((_, k) => `<circle r="4.5" style="fill:${color(k)}"/>`).join("")}</g>`;
  drawn = { x, y, from, n, series, years, W, H, M };
  $("d-cap").innerHTML = topic.terms.map((t, k) => `<span><i style="background:${color(k)}"></i><b lang="fi">${esc(t.term)}</b> ${esc(t.en)}</span>`).join("") +
    `<span class="legend-note">${mode === "share" ? `Share of articles using any of these words${from ? `, from ${data.years[from]} (earlier years have under ${MIN_TOTAL} mentions)` : ""}` : "Articles using each word at the end of the year"}</span>`;
  if (animate && !reduced()) for (const p of svg.querySelectorAll(".line")) {        // explanatory: the lines grow through the years
    p.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], { duration: 900, easing: "cubic-bezier(0.23, 1, 0.32, 1)" });
  }
  if (hover != null) cross(hover);
}

function cross(i) {
  const d = drawn, g = $("d-cross"), tip = $("d-tip");
  if (i == null || !d) { g.style.display = "none"; tip.hidden = true; hover = null; return; }
  hover = i = Math.max(d.from, Math.min(d.from + d.n - 1, i));
  const px = d.x(i);
  g.style.display = "";
  g.querySelector("line").setAttribute("x1", px); g.querySelector("line").setAttribute("x2", px);
  [...g.querySelectorAll("circle")].forEach((c, k) => { c.setAttribute("cx", px); c.setAttribute("cy", d.y(d.series[k][i])); });
  const rows = topic.terms.map((t, k) => ({ t, k, v: d.series[k][i], c: t.counts[i] })).sort((a, b) => b.v - a.v);
  tip.innerHTML = `<b class="num">${data.years[i]}</b>` + rows.map(r => `<span><i style="background:var(${SERIES[r.k]})"></i><span lang="fi">${esc(r.t.term)}</span>
      <b class="num">${fmt(r.v)}</b>${mode === "share" ? `<small class="num">${num(r.c)}</small>` : ""}</span>`).join("");
  tip.hidden = false;
  const left = px + 14 + tip.offsetWidth > d.W ? px - 14 - tip.offsetWidth : px + 14;
  tip.style.transform = `translate(${left}px, ${d.M.t}px)`;
  $("d-chart").querySelector(".chart-plot").setAttribute("aria-label", `${data.years[i]}: ` + rows.map(r => `${r.t.term} ${fmt(r.v)}`).join(", "));
}

const plot = $("d-chart").querySelector(".chart-plot");
plot.addEventListener("pointermove", e => {
  const d = drawn; if (!d) return;
  const r = plot.getBoundingClientRect(), px = (e.clientX - r.left) * (d.W / r.width);
  cross(Math.round(d.from + ((px - d.M.l) / (d.W - d.M.l - d.M.r)) * (d.n - 1)));
});
plot.addEventListener("pointerleave", () => cross(null));
plot.addEventListener("keydown", e => {
  if (!drawn) return;
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); cross((hover ?? drawn.from + drawn.n - 1) + (e.key === "ArrowRight" ? 1 : -1)); }
  if (e.key === "Escape") cross(null);
});
plot.addEventListener("blur", () => cross(null));
let resizeTimer = 0;
addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => topic && draw(false), 120); });

function table() {
  $("d-table").innerHTML = `<table><thead><tr><th scope="col">Year</th>${topic.terms.map(t => `<th scope="col" lang="fi">${esc(t.term)}</th>`).join("")}<th scope="col">All articles</th></tr></thead>
    <tbody>${data.years.map((yr, i) => `<tr><th scope="row">${yr}</th>${topic.terms.map(t => `<td class="num">${num(t.counts[i])}</td>`).join("")}<td class="num">${num(data.articles[i])}</td></tr>`).join("")}</tbody></table>`;
}

// highlight the word (any case ending) in a snippet: its stem plus the rest of the word
const stem = term => term.split(" ").map(w => w.length > 6 ? w.slice(0, w.length - 3) : w).join("\\s+\\p{L}*");
const mark = (text, term, tag) => esc(text).replace(new RegExp(`[\\p{L}-]*${stem(term)}[\\p{L}-]*`, "giu"), m => `<${tag}>${m}</${tag}>`);
const month = iso => new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" });

function flips() {
  const box = $("d-flips"), dir = $("d-dir");
  if (!topic.synonyms) {
    dir.innerHTML = `<p class="muted-note">These words name different things, so a paragraph swapping one for the other is not a rename. The chart shows how often each was used.</p>`;
    box.innerHTML = "";
    return;
  }
  const dirs = topic.directions || [];
  const top = dirs.length ? dirs[0].count : 1;
  dir.innerHTML = `<p>${num(topic.flip_count)} edit${topic.flip_count === 1 ? "" : "s"} replaced one word with another in an article's paragraph.</p>` +
    (dirs.length ? `<ul class="dir-bars">${dirs.slice(0, 5).map(d => `<li><span class="dir-label"><span lang="fi">${esc(d.from)}</span> → <span lang="fi">${esc(d.to)}</span></span>
      <span class="bar" style="--w:${d.count / top}"></span><b class="num">${num(d.count)}</b></li>`).join("")}</ul>` : "");
  box.innerHTML = topic.flips.map(f => `<li class="flip">
      <div class="flip-meta"><span class="num">${month(f.at)}</span><a href="/article/${f.page_id}?as_of=${f.at}" lang="fi">${esc(f.title)}</a>
        <a class="flip-diff" href="https://fi.wikipedia.org/?diff=${f.rev_id}" target="_blank" rel="noopener">See the edit ↗</a></div>
      <p class="flip-text" lang="fi"><span class="was">${mark(f.before, f.from, "del")}</span><span class="now">${mark(f.after, f.to, "ins")}</span></p></li>`).join("") +
    (topic.flip_count > topic.flips.length ? `<li class="flip-more">The first ${topic.flips.length} of ${num(topic.flip_count)}, oldest first.</li>` : "");
}
