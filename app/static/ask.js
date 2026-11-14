// The Ask page (owner: ui). Data comes only through api.js (live route first, fixture fallback).
// The last answer is kept in sessionStorage, so coming back from the graph or history page shows
// it at once (no 8 s refetch) and the clicked title can morph back (view transition).
import { ask, related } from "/static/api.js";

const $ = id => document.getElementById(id);
const root = $("ask"), form = $("ask-form"), input = $("q"), asOf = $("as-of"), clearBtn = $("as-of-clear");
const errorBox = $("ask-error"), statusBox = $("status"), answerBox = $("answer"), sourcesBox = $("sources");
const relatedBox = $("related"), results = $("results");
const params = new URLSearchParams(location.search), mock = params.get("mock");

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);   // all API text goes through this
const num = n => Number(n).toLocaleString("en-US");
const day = iso => iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) : "";
const safeUrl = u => /^https?:\/\//.test(u) ? esc(u) : "#";
const store = {
  get(k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch {} },   // private mode or full: the page works without it
};
const graphUrl = (id, q) => `/graph/${id}?q=${encodeURIComponent(q)}${mock ? "&mock=" + encodeURIComponent(mock) : ""}`;
// "sample data" when api.js fell back to a fixture, with the reason (_error) when the live call failed
const sample = r => r?._source !== "fixture" ? "" : `<span class="pill pill-warn pill-sample" title="${r._error
  ? "The live service did not answer (" + esc(r._error) + "); this is a saved example." : "A saved example (mock mode)."}">sample data${r._error ? " · " + esc(r._error) : ""}</span>`;
const GRAPH_ICON = `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 7l6 10M12 17l7-9M6 7l13 1"/><circle cx="6" cy="7" r="2.4" fill="currentColor"/><circle cx="19" cy="8" r="2" fill="currentColor"/><circle cx="12" cy="17" r="2.2" fill="currentColor"/></svg>`;

let run = 0, saved = null, stepTimers = [], shownSources = new Map();   // shownSources: n -> source on screen

// ---- translation: the browser's on-device translator when it has one (free, private), else the
// backend (Claude). Always labelled as a machine translation; the cited original stays the Finnish text.
const translations = new Map();                        // passage text -> {text, engine}
async function translateText(text) {
  if (translations.has(text)) return translations.get(text);
  let out = null;
  if ("Translator" in self) {
    try {
      const opts = { sourceLanguage: "fi", targetLanguage: "en" };
      if (await Translator.availability(opts) !== "unavailable")
        out = { text: await (await Translator.create(opts)).translate(text), engine: "your browser, on-device" };
    } catch (e) { console.warn("on-device translation failed, using the server:", e); }
  }
  if (!out) {
    const r = await fetch("/api/translate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    const d = await r.json().catch(() => null);
    if (!r.ok || !d?.translation) throw new Error(d?.error || `HTTP ${r.status}`);
    out = { text: d.translation, engine: "Claude" };
  }
  translations.set(text, out);
  return out;
}

async function toggleTranslation(btn) {
  const s = shownSources.get(+btn.dataset.translate), box = $(btn.getAttribute("aria-controls"));
  if (!s || !box) return;
  if (btn.getAttribute("aria-expanded") === "true") {   // showing: hide it again
    box.hidden = true; btn.setAttribute("aria-expanded", "false"); btn.textContent = "Translate";
    return;
  }
  btn.disabled = true; btn.textContent = "Translating…";
  try {
    const t = await translateText(s.text);
    box.replaceChildren(Object.assign(document.createElement("p"), { textContent: t.text }),
      Object.assign(document.createElement("small"), { textContent: `Machine translation (${t.engine}). The cited source is the Finnish text above.` }));
    box.hidden = false; btn.setAttribute("aria-expanded", "true"); btn.textContent = "Hide translation";
  } catch (e) {
    box.replaceChildren(Object.assign(document.createElement("small"), { textContent: "Translation failed: " + e.message }));
    box.hidden = false; btn.textContent = "Translate";
  } finally { btn.disabled = false; }
}

function setState(next) {
  const change = () => { root.dataset.state = next; };
  // leaving the landing page: the question box travels up instead of jumping
  if (root.dataset.state === "landing" && next !== "landing" && document.startViewTransition && !reduced()) document.startViewTransition(change);
  else change();
}

// ---- loading: three status lines (timed hints, not real progress) over a skeleton of the answer
function showLoading() {
  const steps = ["Searching passages", "Reading the sources", "Writing the answer"];
  statusBox.innerHTML = steps.map((s, i) => `<span class="step${i ? "" : " is-active"}"><i></i>${s}…</span>`).join("");
  stepTimers.forEach(clearTimeout);
  stepTimers = [900, 2400].map((ms, i) => setTimeout(() => {
    statusBox.children[i].className = "step is-done";
    statusBox.children[i + 1].className = "step is-active";
  }, ms));
  const line = (w, h) => `<div class="sk" style="width:${w}%${h ? `;height:${h}` : ""}"></div>`;
  answerBox.innerHTML = `<div aria-hidden="true">${[96, 100, 91, 97, 58].map(w => line(w)).join("")}</div>`;
  sourcesBox.innerHTML = `<div class="src is-skeleton" aria-hidden="true">${line(46)}${line(24, ".7rem")}${line(100)}${line(93)}${line(71)}</div>`.repeat(2);
  relatedBox.hidden = true;
  results.classList.remove("is-arriving");
  results.setAttribute("aria-busy", "true");
}

// ---- the answer --------------------------------------------------------------------------------
function render(res, q, animate) {
  stepTimers.forEach(clearTimeout);
  const tvn = res.kind === "then_vs_now", srcs = res.sources || [], byN = new Map(srcs.map(s => [s.n, s]));
  shownSources = byN;
  const year = (res.as_of || "").slice(0, 4);
  let i = 0;                                            // order of arrival (the stagger)

  const sentence = a => {
    const cites = (a.cites || []).filter(n => byN.has(n));
    const text = esc(String(a.text).replace(/\s*\[\d+\]/g, ""));         // markers come from cites, not from the text
    return cites.length
      ? `<span class="sent" data-cites="${cites.join(" ")}" style="--i:${i++}">${text}${cites.map(n =>
          `<button class="cite" type="button" data-n="${n}" aria-label="Source ${n}: ${esc(byN.get(n).title)}">${n}</button>`).join("")}</span> `
      : `<span class="sent uncited" style="--i:${i++}" title="No source is cited for this sentence">${text}<span class="pill pill-warn tag-uncited">uncited</span></span> `;
  };
  const part = (label, list) => !list.length ? "" :
    `<div class="answer-part">${label ? `<h2 class="kicker" style="--i:${i}">${label}</h2>` : ""}<p class="answer-text">${list.map(sentence).join("")}</p></div>`;
  const isThen = a => a.cites?.length && a.cites.every(n => byN.get(n)?.era === "then");

  const mark = ([op, t]) => op === "equal" ? esc(t) : op === "delete" ? `<del>${esc(t)}</del>` : `<ins>${esc(t)}</ins>`;
  const diff = d => {
    const a = byN.get(d.then), b = byN.get(d.now), s = b || a || {}, ops = d.ops || [];
    const only = keep => ops.filter(([op]) => op === "equal" || op === keep).map(mark).join(" ");
    const link = (x, label) => x ? `<a href="${safeUrl(x.url)}" target="_blank" rel="noopener">${label} [${x.n}] ↗</a>` : "";
    return `<article class="diff"><div class="diff-head">
        <strong lang="fi">${esc(s.title)}${s.heading ? " · " + esc(s.heading) : ""}</strong>
        ${link(a, (year || "old") + " version")}<span aria-hidden="true">→</span>${link(b, "version now")}
        <span class="pill num" title="How much of the old paragraph is still there">${Math.round(d.similarity * 100)}% the same</span></div>` +
      (d.similarity < 0.5                               // mostly rewritten: side by side reads better
        ? `<div class="diff-cols"><div><h4 class="kicker">Then</h4><p class="diff-body" lang="fi">${only("delete")}</p></div>
           <div><h4 class="kicker">Now</h4><p class="diff-body" lang="fi">${only("insert")}</p></div></div>`
        : `<p class="diff-body" lang="fi">${ops.map(mark).join(" ")}</p>`) + `</article>`;
  };

  const answer = res.answer || [];
  answerBox.innerHTML = (tvn
    ? part(`In ${year || "the past"} Wikipedia said`, answer.filter(isThen)) + part("What changed since", answer.filter(a => !isThen(a)))
    : part("", answer)) +
    (tvn && res.diffs?.length ? `<section class="diffs"><h2 class="kicker">What changed in the text
       <span class="diff-key"><del>removed</del><ins>added</ins></span></h2>${res.diffs.map(diff).join("")}</section>` : "");

  const card = (s, j) => {
    const h = s.health, key = `src-${s.n}`;
    const history = `/article/${s.page_id}` + (s.era === "then" && res.as_of ? `?as_of=${encodeURIComponent(res.as_of.slice(0, 10))}` : "");
    return `<article class="src" id="${key}" data-n="${s.n}"${s.era ? ` data-era="${esc(s.era)}"` : ""} tabindex="-1" style="--i:${j}">
      <header><span class="n" aria-hidden="true">${s.n}</span><div>
        <h3 lang="fi" data-morph="${key}">${esc(s.title)}</h3>
        <p class="src-heading">${esc(s.heading || "Lead")}</p></div></header>
      <p class="src-text clamp" id="${key}-text" lang="fi">${esc(s.text)}</p>
      <button class="linkish more" type="button" aria-expanded="false" aria-controls="${key}-text" hidden>Show more</button>
      <p class="src-meta">${s.edits != null ? `<span class="num">${num(s.edits)} edits · ${num(s.reverts || 0)} reverts</span>` : ""}${!h ? "" :
        (h.live_since ? `<span class="pill" title="This passage has stood in the article since ${esc(h.live_since)}">live since ${esc(h.live_since.slice(0, 4))}</span>` : "") +
        (h.rewrites != null ? `<span class="pill num">${num(h.rewrites)} rewrite${h.rewrites === 1 ? "" : "s"}</span>` : "") +
        (h.contested ? `<span class="pill pill-warn" title="This passage is often reverted">contested</span>` : "")}</p>
      <div class="src-translation" id="${key}-en" lang="en" hidden></div>
      <div class="src-actions">
        <a class="btn btn-quiet" href="${safeUrl(s.deep_url || s.url)}" target="_blank" rel="noopener" title="The exact version this text came from, scrolled to this passage">Open on Wikipedia ↗</a>
        <a class="btn btn-quiet" href="${history}" data-go="${key}">History</a>
        <a class="btn btn-quiet" href="${graphUrl(s.page_id, q)}" data-go="${key}">Graph</a>
        <button class="btn btn-quiet" type="button" data-translate="${s.n}" aria-controls="${key}-en" aria-expanded="false">Translate</button>
        ${s.other_langs?.en ? `<a class="btn btn-quiet" href="${safeUrl(s.other_langs.en.url)}" target="_blank" rel="noopener" lang="en"
            title="The same topic on English Wikipedia: ${esc(s.other_langs.en.title)} (a different text, not a translation)">English Wikipedia ↗</a>` : ""}
      </div></article>`;
  };
  const group = (label, list, from) => !list.length ? "" :
    `<h2 class="kicker era" style="--i:${from}">${label}</h2>` + list.map((s, j) => card(s, from + j)).join("");
  const then = tvn ? srcs.filter(s => s.era === "then") : [], rest = srcs.filter(s => !then.includes(s));
  sourcesBox.innerHTML = tvn
    ? group(["Then", day(res.as_of)].filter(Boolean).join(" · "), then, 0) + group(["Now", day(res.compare_to)].filter(Boolean).join(" · "), rest, then.length)
    : group("Sources", rest, 0);

  statusBox.innerHTML = `<span class="kicker">Answer</span>${tvn ? `<span class="pill pill-accent">then vs now</span>` : ""}
    <span>${srcs.length} source${srcs.length === 1 ? "" : "s"}, each linked to its exact version</span>${sample(res)}`;
  results.classList.toggle("is-arriving", animate);
  results.dataset.kind = tvn ? "tvn" : "plain";
  results.removeAttribute("aria-busy");
  remember(srcs.map(s => [s.page_id, s.title]));
}

// "Show more" only where the text really is cut; needs the results visible (and the stylesheet loaded)
function measure() {
  for (const p of sourcesBox.querySelectorAll(".src-text.clamp")) p.nextElementSibling.hidden = p.scrollHeight <= p.clientHeight + 1;
}
addEventListener("load", measure);

function renderRelated(rel, q, animate) {
  const list = rel?.articles || [];
  relatedBox.hidden = !list.length;
  relatedBox.classList.toggle("is-arriving", animate);
  relatedBox.innerHTML = !list.length ? "" : `<h2 class="kicker">Related articles ${sample(rel)}</h2>
    <p>Open one as a graph: the article, its neighbours, and how the links between them grew.</p>
    <ol class="rel-list">${list.map(a => `<li class="rel"><div>
      <h3 lang="fi" data-morph="rel-${a.page_id}">${esc(a.title)}</h3><p class="clamp" lang="fi">${esc(a.snippet)}</p></div>
      <a class="btn" href="${graphUrl(a.page_id, q)}" data-go="rel-${a.page_id}" aria-label="Graph of ${esc(a.title)}">${GRAPH_ICON}Graph</a></li>`).join("")}</ol>`;
  remember(list.map(a => [a.page_id, a.title]));
}

function remember(pairs) {                              // titles for the next page's heading (graph.html reads this)
  const t = store.get("titles") || {};
  for (const [id, title] of pairs) t[id] = title;
  store.set("titles", t);
}

function save(patch) { saved = { ...saved, ...patch }; store.set("lastAsk", saved); }

function loadRelated(promise, q, id, animate) {
  promise.then(rel => { if (id === run) { renderRelated(rel, q, animate); save({ rel }); } }).catch(() => {});
}

// ---- asking ------------------------------------------------------------------------------------
async function submit() {
  const q = input.value.trim(), date = asOf.value, id = ++run, t0 = performance.now();
  errorBox.replaceChildren();
  if (q) { showLoading(); setState("loading"); }
  const rel = q ? related(q) : null;
  rel?.catch(() => {});                                // handled again in loadRelated; no stray rejection if ask fails
  try {
    const res = await ask(q, date || undefined);
    await new Promise(r => setTimeout(r, 450 - (performance.now() - t0)));   // a very fast reply must not flash the skeleton
    if (id !== run) return;                              // a newer question took over
    setState("answer");
    render(res, q, true);
    measure();
    saved = null; save({ q, asOf: date, res });
    const p = new URLSearchParams(location.search);     // keep the address shareable (and ?mock=1)
    p.set("q", q); date ? p.set("as_of", date) : p.delete("as_of");
    history.replaceState(null, "", "?" + p);
    document.title = q + " · Wikipedia trust tool";
    loadRelated(rel, q, id, true);
  } catch (e) {
    if (id !== run) return;
    stepTimers.forEach(clearTimeout);
    if (q) setState("error"); else input.focus();
    errorBox.innerHTML = `<p class="alert"><span><b>${q ? "That did not work." : "Type a question first."}</b> ${esc(e.message)}</span>
      ${q ? `<button class="btn" type="button">Try again</button>` : ""}</p>`;
  }
}

form.addEventListener("submit", e => { e.preventDefault(); submit(); });
errorBox.addEventListener("click", e => { if (e.target.closest("button")) submit(); });
$("examples").addEventListener("click", e => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  input.value = chip.dataset.q || chip.textContent.trim();
  asOf.value = ""; clearBtn.hidden = true;
  submit();
});
asOf.addEventListener("input", () => { clearBtn.hidden = !asOf.value; });
clearBtn.addEventListener("click", () => { asOf.value = ""; clearBtn.hidden = true; asOf.focus(); });

// ---- sentence <-> source: hover or focus one side, the other lights up; a marker jumps to its card
function highlight(ns) {
  for (const e of results.querySelectorAll(".is-hl")) e.classList.remove("is-hl");
  for (const n of ns) for (const e of results.querySelectorAll(`.src[data-n="${n}"], .cite[data-n="${n}"], .sent[data-cites~="${n}"]`)) e.classList.add("is-hl");
}
const cited = t => {
  const e = t.closest?.(".cite, .src, .sent");
  return !e ? [] : e.dataset.n ? [e.dataset.n] : (e.dataset.cites || "").split(" ").filter(Boolean);
};
results.addEventListener("pointerover", e => highlight(cited(e.target)));
results.addEventListener("pointerleave", () => highlight([]));
results.addEventListener("focusin", e => highlight(cited(e.target)));
results.addEventListener("focusout", () => highlight([]));
results.addEventListener("click", e => {
  const cite = e.target.closest(".cite"), more = e.target.closest(".more"), go = e.target.closest("[data-go]");
  const tr = e.target.closest("[data-translate]");
  if (tr) toggleTranslation(tr);
  else if (cite) {
    const card = $("src-" + cite.dataset.n);
    card.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
    card.focus({ preventScroll: true });               // the focused card keeps its ring; Tab goes on to its links
  } else if (more) {
    const open = more.getAttribute("aria-expanded") !== "true";
    more.previousElementSibling.classList.toggle("clamp", !open);
    more.setAttribute("aria-expanded", open);
    more.textContent = open ? "Show less" : "Show more";
  } else if (go) {
    morph(go.dataset.go);
    save({ morph: go.dataset.go });
  }
});

// The clicked article title becomes the next page's heading, and morphs back on return.
function morph(key) {
  for (const e of results.querySelectorAll("[data-morph]")) e.style.viewTransitionName = e.dataset.morph === key ? "article-title" : "";
}

// ---- start: a question in the address is restored from this tab's cache, or asked -----------------
const q0 = (params.get("q") || "").trim();
saved = store.get("lastAsk");
if (q0) {
  input.value = q0;
  const date = params.get("as_of");
  if (saved?.res && saved.q === q0 && (!date || date === saved.asOf)) {
    asOf.value = saved.asOf || "";
    root.dataset.state = "answer";
    render(saved.res, q0, false);
    measure();
    if (saved.rel) renderRelated(saved.rel, q0, false); else loadRelated(related(q0), q0, run, false);
    if (saved.morph) morph(saved.morph);
    document.title = q0 + " · Wikipedia trust tool";
  } else {
    asOf.value = date || "";
    root.dataset.state = "loading";                     // straight to the results layout, nothing to travel from
    submit();
  }
} else if (matchMedia("(pointer: fine)").matches) input.focus({ preventScroll: true });
clearBtn.hidden = !asOf.value;
