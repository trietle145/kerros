// Graph page wiring: load the data, start the canvas (core.js), and fill the containers that
// graph.html provides: #graph-timeline, #graph-panel, #graph-legend, #graph-nodelist, #graph-status.
// A missing container is skipped with one console warning.
import * as api from "/static/api.js";
import { stateFor, counts } from "/static/graph/time.js";
import { createPanel, oftenReverted, REL, el, dot, reduced } from "/static/graph/panel.js";

const STEP_MS = 800;                                   // one year per step while playing
const box = name => document.getElementById("graph-" + name) || (console.warn(`graph: #graph-${name} is missing, skipped`), null);
const params = new URLSearchParams(location.search);
const q = document.body.dataset.q || params.get("q") || "";
const pageId = document.body.dataset.pageId || location.pathname.split("/").filter(Boolean).pop();

const status = box("status");
function say(...kids) { status?.replaceChildren(...kids); }

function graphUrl(id) {                                // "Make this the main node": same question, same mock mode
  const p = new URLSearchParams({ q });
  if (params.get("mock")) p.set("mock", params.get("mock"));
  return `/graph/${id}?${p}`;
}

if (!document.querySelector('link[href*="graph/graph.css"]'))   // in case graph.html does not link it
  document.head.append(el("link", { rel: "stylesheet", href: "/static/graph/graph.css" }));
start();

async function start() {
  say(el("span.g-spin", { "aria-hidden": "true" }), "Loading the graph…");
  let data;
  try {
    data = await api.graph(pageId);
    if (!data.nodes?.length || !data.years?.length) throw new Error("the graph is empty");
  } catch (e) {
    console.warn("graph:", e);
    return say(el("span.g-err", null, "The graph could not be loaded. "), el("button.g-btn", { type: "button", onclick: start }, "Try again"));
  }

  const canvas = box("canvas");
  let g = new Proxy({}, { get: () => () => {} });      // no canvas: the list, panel and timeline still work
  let broken = !canvas;
  try {
    const { createGraph } = await import("/static/graph/core.js");
    if (canvas) g = createGraph(canvas, { nodes: data.nodes, main: data.main });
  } catch (e) {
    console.warn("graph: the canvas could not start:", e);
    broken = true;
  }

  const byId = new Map(data.nodes.map(n => [n.id, n]));
  const mainTitle = byId.get(data.main)?.title || "";
  say(...[
    broken && el("span.g-err", null, "The drawing could not start; the article list below still works."),
    data._source === "fixture" && el("span.g-note", null,
      "Sample data" + (String(data.main) !== String(pageId) ? `: no graph for article ${pageId}, showing ${mainTitle}` : ""),
      data._error && el("span.g-why", null, ` · live graph unavailable (${data._error})`)),
  ].filter(Boolean));

  const years = data.years, last = years.length - 1;
  let index = last, selected = null, shown = new Set();   // shown: the ids visible in the year on screen

  // ---- selection: canvas, list and panel stay in sync ------------------------------------------
  const panelBox = box("panel"), listBox = box("nodelist");
  const panel = panelBox && createPanel(panelBox, { data, g, q, api, graphUrl, select: id => select(id, true) });
  const items = new Map();                              // id -> its button in the list

  function select(id, focus) {
    if (id != null && !byId.has(id)) id = null;
    if (id !== selected) {
      items.get(selected)?.setAttribute("aria-pressed", "false");
      selected = id;
      items.get(id)?.setAttribute("aria-pressed", "true");
      items.get(id)?.scrollIntoView({ block: "nearest" });
      g.select(id);
      panel?.show(id == null ? null : byId.get(id));
    }
    if (focus && shown.has(id)) g.focus(id);            // never fly to a node that is not there that year
  }
  g.on("select", id => select(id));
  g.on("hover", id => { for (const [nid, b] of items) b.classList.toggle("is-hover", nid === id); });
  addEventListener("keydown", e => { if (e.key === "Escape" && selected != null) select(null); });
  if (canvas && window.ResizeObserver) new ResizeObserver(() => g.resize()).observe(canvas);

  // ---- the accessible list of nodes ------------------------------------------------------------
  const order = Object.keys(REL).filter(r => data.nodes.some(n => n.relation === r));   // the relations in this graph
  const hot = oftenReverted(data.nodes);
  if (listBox) {
    const hover = id => g.hover?.(id);                  // core.js offers it, outside the contract
    listBox.replaceChildren(...order.map(r =>
      el("section.gl-group", null,
        el("h4", null, dot(r), REL[r].label),
        el("ul.gl", { "aria-label": REL[r].label }, data.nodes.filter(n => n.relation === r)
          .sort((a, b) => a.title.localeCompare(b.title, "fi")).map(n => {
            const b = el("button", { type: "button", "aria-pressed": "false", onclick: () => select(n.id, true),
              onmouseenter: () => hover(n.id), onmouseleave: () => hover(null), onfocus: () => hover(n.id), onblur: () => hover(null) },
              el("span.gl-t", { lang: "fi" }, n.title),
              hot.has(n.id) && el("span.g-ring", { role: "img", "aria-label": "often reverted", title: "Often reverted" }));
            items.set(n.id, b);
            return el("li", null, b);
          })))));
  }

  // ---- legend ----------------------------------------------------------------------------------
  box("legend")?.replaceChildren(el("ul.gg", { "aria-label": "Legend" },
    order.map(r => el("li", null, dot(r), REL[r].label, r === "related" && el("span.gg-line.gg-dashed", { "aria-hidden": "true" }))),
    el("li", null, el("span.g-ring", { "aria-hidden": "true" }), "Often reverted"),
    el("li", null, el("span.g-dot.gg-small", { "aria-hidden": "true" }), el("span.g-dot.gg-big", { "aria-hidden": "true" }), "Bigger: more links here"),
    el("li", null, el("span.gg-line.gg-arrow", { "aria-hidden": "true" }), "Arrow: links one way only"),
    years.length > 1 && el("li", null, el("span.gg-line.gg-added", { "aria-hidden": "true" }), "Link added",
      el("span.gg-line.gg-removed", { "aria-hidden": "true" }), "removed that year")));

  // ---- timeline --------------------------------------------------------------------------------
  const per = counts(data), maxLinks = Math.max(1, ...per.map(c => c.links));
  const tl = box("timeline");
  const icon = d => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
  const PLAY = icon("M8 5.1v13.8a1 1 0 0 0 1.5.9l11-6.9a1 1 0 0 0 0-1.8l-11-6.9A1 1 0 0 0 8 5.1z"), PAUSE = icon("M7 5h3.5v14H7zM13.5 5H17v14h-3.5z");
  const playBtn = el("button.gt-play", { type: "button", "aria-label": "Play the years", disabled: last === 0, onclick: () => toggle() });
  const yearOut = el("output.gt-year"), nNodes = el("b"), nLinks = el("b"), wNodes = el("span"), wLinks = el("span");
  const range = el("input", { type: "range", min: 0, max: last, step: 1, "aria-label": "Year", disabled: last === 0,
    oninput: () => { pause(); hideHint(); setIndex(+range.value); } });
  const bars = per.map(c => el("i", { style: `--h:${(c.links / maxLinks).toFixed(3)}` }));
  let hint = null, timer = null;
  try { if (last > 0 && !localStorage.graphPlayed) hint = el("p.gt-hint", null, "Press play to watch the connections grow"); } catch {}
  tl?.replaceChildren(el("div.gt", { role: "group", "aria-label": "Timeline" },
    playBtn,
    el("div.gt-now", null, yearOut, el("span.gt-counts", null, nNodes, " ", wNodes, " · ", nLinks, " ", wLinks)),
    el("div.gt-track", null,
      el("div.gt-spark", { "aria-hidden": "true", title: "Links per year" }, bars),
      range,
      el("div.gt-ends", { "aria-hidden": "true" }, el("span", null, years[0]), last > 0 && el("span", null, years[last]))),
    hint));
  if (hint) playBtn.classList.add("is-inviting");

  function hideHint() {
    if (!hint) return;
    hint.classList.add("is-gone"); playBtn.classList.remove("is-inviting"); hint = null;
    try { localStorage.graphPlayed = "1"; } catch {}
  }

  function tick(node, to) {                             // count up or down to the new number
    cancelAnimationFrame(node._raf);
    const from = +node.textContent || 0, t0 = performance.now();
    if (reduced() || from === to || !node.textContent) return void (node.textContent = to);
    const step = now => {
      const k = Math.min(1, (now - t0) / 260);
      node.textContent = Math.round(from + (to - from) * (1 - (1 - k) ** 3));
      if (k < 1) node._raf = requestAnimationFrame(step);
    };
    node._raf = requestAnimationFrame(step);
  }

  // Show year i. quiet = no added/removed flashes (first draw, and the jump back when replaying).
  function setIndex(i, quiet) {
    const year = years[i], prev = quiet ? null : years[index];
    index = i;
    const s = stateFor(data, year, prev);
    g.apply(s);
    shown = s.visible;
    panel?.setYear(year);
    for (const [id, b] of items) b.parentNode.hidden = !s.visible.has(id);
    for (const grp of listBox?.children || []) grp.hidden = !grp.querySelector("li:not([hidden])");
    if (!tl) return;
    range.value = i;
    range.style.setProperty("--p", last ? i / last : 1);
    range.setAttribute("aria-valuetext", `${year}: ${s.visible.size} articles, ${s.links.length} links`);
    yearOut.textContent = year;
    tick(nNodes, s.visible.size); tick(nLinks, s.links.length);
    wNodes.textContent = s.visible.size === 1 ? "article" : "articles";
    wLinks.textContent = s.links.length === 1 ? "link" : "links";
    bars.forEach((b, j) => { b.classList.toggle("is-on", j <= i); b.classList.toggle("is-now", j === i); });
  }

  function pause() {
    clearInterval(timer); timer = null;
    playBtn.innerHTML = PLAY;
    playBtn.setAttribute("aria-label", index === last ? "Replay the years" : "Play the years");
    playBtn.classList.remove("is-playing");
  }
  function toggle() {
    if (timer) return pause();
    if (last === 0) return;
    hideHint();
    if (index === last) setIndex(0, true);              // at the end: start again from the first year
    playBtn.innerHTML = PAUSE;
    playBtn.setAttribute("aria-label", "Pause");
    playBtn.classList.add("is-playing");
    timer = setInterval(() => { setIndex(index + 1); if (index === last) pause(); }, STEP_MS);
  }
  // Space plays or pauses from anywhere except controls that use Space themselves
  addEventListener("keydown", e => {
    if (e.key !== " " || !tl || e.target.closest?.("button, a, select, textarea, input:not([type=range])")) return;
    e.preventDefault();
    toggle();
  });

  setIndex(last, true);
  pause();
}
