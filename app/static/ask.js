// The Ask page (owner: ui). Data comes only through api.js (live route first, fixture fallback).
// The last answer is kept in sessionStorage, so coming back from the graph or history page shows
// it at once (no 8 s refetch) and the clicked title can morph back (view transition).
import { ask, related, health, rewind } from "/static/api.js";

const $ = id => document.getElementById(id);
const root = $("ask"), form = $("ask-form"), input = $("q"), asOf = $("as-of"), clearBtn = $("as-of-clear");
const errorBox = $("ask-error"), statusBox = $("status"), answerBox = $("answer"), pop = $("cite-pop");
const relatedBox = $("related"), results = $("results"), scopeBox = $("scope-l");
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

let run = 0, saved = null, stepTimers = [], current = null, ctrl = null;   // current = {res, q, byN} of the answer on screen

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
  const note = html => { statusBox.querySelector(".slow")?.remove(); statusBox.insertAdjacentHTML("beforeend", `<span class="slow">${html}</span>`); };
  stepTimers.push(setTimeout(() => note(`Still writing; answers about the past take up to 20 s. <button class="linkish" type="button" data-act="cancel">Cancel</button>`), 8000),
                  setTimeout(() => note(`This is taking unusually long. <button class="linkish" type="button" data-act="cancel">Cancel</button> or <a href="?mock=1&q=${encodeURIComponent(input.value.trim())}">see a saved example</a>`), 25000));
  const line = (w, h) => `<div class="sk" style="width:${w}%${h ? `;height:${h}` : ""}"></div>`;
  closePop(false);
  answerBox.innerHTML = `<div aria-hidden="true">${[96, 100, 91, 97, 58].map(w => line(w)).join("")}</div>`;
  relatedBox.hidden = true;
  results.classList.remove("is-arriving");
  results.setAttribute("aria-busy", "true");
}

// ---- the answer --------------------------------------------------------------------------------
function render(res, q, animate) {
  stepTimers.forEach(clearTimeout);
  const tvn = res.kind === "then_vs_now", srcs = res.sources || [], byN = new Map(srcs.map(s => [s.n, s]));
  const year = (res.as_of || "").slice(0, 4);
  let i = 0;                                            // order of arrival (the stagger)

  const answer = res.answer || [];
  const sentence = a => {
    const cites = (a.cites || []).filter(n => byN.has(n)), k = answer.indexOf(a);
    const text = esc(String(a.text).replace(/\s*\[\d+\]/g, ""));         // markers come from cites, not from the text
    return cites.length
      ? `<span class="sent" data-a="${k}" data-cites="${cites.join(" ")}" style="--i:${i++}"><span class="sent-t">${text}</span>${cites.map(n => { const s = byN.get(n);
          return `<button class="cite" type="button" data-n="${n}"${s.era ? ` data-era="${esc(s.era)}"` : ""} aria-haspopup="dialog" aria-expanded="false" aria-controls="cite-pop" aria-label="Source ${n}: ${esc(s.title)}${s.era === "then" ? ", the past version" : ""}">${n}</button>`; }).join("")}</span> `
      : `<span class="sent uncited" style="--i:${i++}" title="No source is cited for this sentence"><span class="sent-t">${text}</span><span class="pill pill-warn tag-uncited">uncited</span></span> `;
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

  // every source in one quiet row under the answer: the cited ones, then the retrieved-but-uncited
  const used = new Set(answer.flatMap(a => a.cites || []));
  const chip = s => `<button class="src-chip" type="button" data-n="${s.n}"${s.era ? ` data-era="${esc(s.era)}"` : ""} aria-haspopup="dialog" aria-expanded="false" aria-controls="cite-pop">
      <span class="n" aria-hidden="true">${s.n}</span><span class="t" lang="fi">${esc(s.title)}</span><span class="h">${esc(s.heading || "Introduction")}</span><i class="dot" aria-hidden="true"></i></button>`;
  const citedSrcs = srcs.filter(s => used.has(s.n)), rest = srcs.filter(s => !used.has(s.n));
  const strip = !srcs.length ? "" : `<section class="src-strip" aria-label="Sources">
      <h2 class="kicker">Sources</h2><div class="chips">${citedSrcs.map(chip).join("")}</div>
      ${rest.length ? `<details class="also"><summary>${rest.length} more passage${rest.length === 1 ? "" : "s"} found, not cited</summary><div class="chips">${rest.map(chip).join("")}</div></details>` : ""}
      <p class="license">Text from Finnish Wikipedia, <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>. Each source opens the exact version it came from.</p></section>`;
  // "Show in English / Finnish" (app/translate.py): only the sentence text changes, the citation buttons stay
  const to = res.lang === "en" ? "fi" : "en", toLabel = to === "fi" ? "Näytä suomeksi · Show in Finnish" : "Show in English";
  const tools = res.lang && answer.some(a => a.cites?.length) ? `<p class="ans-tools"><button class="linkish ans-tr" type="button"
      data-to="${to}" data-label="${toLabel}">${toLabel}</button> <span class="ans-mt" hidden>Machine translation (Opus-MT); citations unchanged</span></p>` : "";
  // what English / Swedish Wikipedia add (app/xlang.py): only when the backend found something
  const xlang = !tvn && res.xlang?.length ? `<section class="xl-adds"><h2 class="kicker">Other Wikipedias add</h2>
      <p class="xl-note">What English and Swedish Wikipedia say about this that the Finnish article does not.</p>${res.xlang.map(x => {
        const lang = x.lang === "sv" ? "sv" : "en", name = lang === "sv" ? "Swedish" : "English";
        return `<div class="xl-add"><span class="xl-lang">${lang.toUpperCase()}</span><div>
          <p class="xl-where" lang="${lang}">${esc(x.title)} › ${esc(x.heading || "Lead")}</p>
          <p class="xl-text" lang="${lang}">${esc(x.text)}</p>
          <a href="${safeUrl(x.url)}" target="_blank" rel="noopener">Read on ${name} Wikipedia ↗</a></div></div>`;
      }).join("")}</section>` : "";
  answerBox.innerHTML = tools + (tvn
    ? part(`In ${year || "the past"} Wikipedia said`, answer.filter(isThen)) + part("What changed since", answer.filter(a => !isThen(a)))
    : part("", answer)) + strip +
    (tvn && res.diffs?.length ? `<section class="diffs"><h2 class="kicker">What changed in the text
       <span class="diff-key"><del>removed</del><ins>added</ins></span></h2>${res.diffs.map(diff).join("")}</section>` : "") + xlang;

  closePop(false);
  current = { res, q, byN };
  setupRewind(res);
  if (tvn && res.as_of && !asOf.value) { asOf.value = res.as_of.slice(0, 10); clearBtn.hidden = false; }   // say which date was answered
  const hint = store.get("citeHint") ? "" : `<span class="hint">${fine.matches ? "Point at a number to preview its source, click to open it" : "Tap a number to see its source"}</span>`;
  store.set("citeHint", 1);
  statusBox.innerHTML = `<span class="kicker">Answer</span>${tvn ? `<span class="pill pill-accent">then vs now</span>` : ""}
    <span>${srcs.length} source${srcs.length === 1 ? "" : "s"}</span>${hint}${sample(res)}`;
  results.classList.toggle("is-arriving", animate);
  results.dataset.kind = tvn ? "tvn" : "plain";
  results.removeAttribute("aria-busy");
  remember(srcs.map(s => [s.page_id, s.title]));
}

// ---- the source popover --------------------------------------------------------------------------
// One element for every source: a short preview while pointing at (or tabbing to) a [n] marker or a
// source chip, the full card on click. Desktop: anchored to its trigger inside .answer-wrap (so it
// scrolls with the text), above the marker when there is room, since that text is already read.
// Phone width: a bottom sheet with a Close button over a scrim.
const fine = matchMedia("(hover: hover) and (pointer: fine)");
const narrow = matchMedia("(max-width: 52rem)");
const EASE = "cubic-bezier(0.23, 1, 0.32, 1)", DRAWER = "cubic-bezier(0.32, 0.72, 0, 1)";
const ANCHOR = ".cite, .src-chip";
const scrim = $("cite-scrim");
let popN = null, popCite = null, peekTimer = 0, hideTimer = 0, lastPeek = 0;

// Which sentence of the passage backs the claim: the one sharing the most word stems (first 5
// letters; numbers whole) with the answer sentence. Matching words get <mark>.
const stems = t => (t.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) || []).map(w => /^\d+$/.test(w) ? w : w.slice(0, 5));
const splitSentences = t => t.split(/\n+|(?<=[.!?])\s+(?=[A-ZÅÄÖ0-9"“(])/).filter(s => s.trim());
function support(text, claim) {
  const sents = splitSentences(String(text || ""));
  const keys = new Set(claim ? stems(claim) : []);
  let best = 0, top = 0;
  sents.forEach((s, i) => {
    let k = 0;
    for (const w of new Set(stems(s))) if (keys.has(w)) k++;
    if (k > top) { top = k; best = i; }
  });
  return { sents: sents.length ? sents : [String(text || "")], i: best, keys: top ? keys : new Set() };
}
const marked = (s, keys) => esc(s).replace(/[\p{L}\p{N}]{4,}/gu, w => keys.has(/^\d+$/.test(w) ? w : w.toLowerCase().slice(0, 5)) ? `<mark>${w}</mark>` : w);

// The answer sentence a marker sits in (chips have none: the passage then starts at its top).
const claimOf = el => { const k = el.closest(".sent")?.dataset.a; return k == null ? "" : current.res.answer[k]?.text || ""; };

const healthPills = h => !h ? "" :
  (h.live_since ? `<span class="pill pill-ok" title="This exact text has stood in the article since ${esc(h.live_since)}">unchanged since ${esc(h.live_since.slice(0, 4))}</span>` : "") +
  (h.rewrites > 1 ? `<span class="pill num" title="Different versions this section has had since it was written">${num(h.rewrites)} versions</span>` : "") +
  (h.contested ? `<span class="pill pill-warn" title="Earlier versions of this section were restored ${num(h.comebacks || 0)} times: a sign of disagreement">often restored</span>` : "");

// does the article exist on English / Swedish Wikipedia too (app/xlang.py: sources carry langs)
const LANG_NAME = { en: "English", sv: "Swedish" };
const langPill = s => !s.langs ? "" : s.langs.length
  ? `<span class="pill pill-xl" title="The same article exists on ${s.langs.map(l => LANG_NAME[l]).join(" and ")} Wikipedia">also in ${s.langs.map(l => LANG_NAME[l]).join(" and ")}</span>`
  : `<span class="pill" title="No English or Swedish article on this topic">only in Finnish</span>`;

function popHtml(s, full, claim) {
  const { res, q } = current, key = `src-${s.n}`, sup = support(s.text, claim);
  const era = !s.era ? "" : `<span class="pill${s.era === "then" ? " pill-warn" : ""}">${
    [s.era === "then" ? "Then" : "Now", day(s.era === "then" ? res.as_of : res.compare_to)].filter(Boolean).join(" · ")}</span>`;
  const head = `<header><span class="n" aria-hidden="true">${s.n}</span><div>
      <h3 lang="fi" data-morph="${key}">${esc(s.title)}</h3>
      <p class="src-heading">${esc(s.heading || "Introduction")}</p></div>${era}
      ${full ? `<button class="pop-close" type="button" aria-label="Close source ${s.n}">✕</button>` : ""}</header>`;
  const lead = sup.i > 0 ? "… " : "";
  if (!full) {
    const hint = !store.get("peekHint") ? `<p class="pop-hint">${fine.matches ? "Click" : "Tap"} for the full source</p>` : "";
    return head + `<p class="src-text clamp clamp-3" lang="fi">${lead}${marked(sup.sents[sup.i], sup.keys)}</p>${hint}`;
  }
  const from = Math.max(0, sup.i - 1), to = Math.min(sup.sents.length, sup.i + 2);
  const excerpt = sup.sents.slice(from, to).map((x, j) => from + j === sup.i ? `<span class="support">${marked(x, sup.keys)}</span>` : esc(x)).join(" ");
  const whole = sup.sents.map((x, j) => j === sup.i ? `<span class="support">${marked(x, sup.keys)}</span>` : esc(x)).join(" ");
  const cut = from > 0 || to < sup.sents.length;
  const history = `/article/${s.page_id}` + (s.era === "then" && res.as_of ? `?as_of=${encodeURIComponent(res.as_of.slice(0, 10))}` : "");
  const rw = s.rewind;                                  // set while the rewind slider shows a past year
  return head + (rw ? rewindNote(rw) : "") +
    `<p class="src-text" id="${key}-text" lang="fi" data-full="${esc(whole)}">${rw?.html || (from > 0 ? "… " : "") + excerpt + (to < sup.sents.length ? " …" : "")}</p>
    ${cut && !rw?.html ? `<button class="linkish more" type="button" aria-expanded="false" aria-controls="${key}-text">Show the whole passage</button>` : ""}
    ${rw?.html ? "" : `<button class="linkish tr-btn" type="button" data-target="${key}-text">Translate</button>`}
    <p class="src-meta">${healthPills(s.health)}${langPill(s)}${s.edits != null ? `<span class="num" title="Counts for the whole article">article: ${num(s.edits)} edits · ${num(s.reverts || 0)} reverts</span>` : ""}</p>
    <div class="src-actions">
      <a class="btn btn-quiet" href="${safeUrl(rw?.url || s.deep_url || s.url)}" target="_blank" rel="noopener" title="The exact version this text came from">Open on Wikipedia ↗</a>
      <a class="btn btn-quiet" href="${history}" data-go="${key}">History</a>
      <a class="btn btn-quiet" href="${graphUrl(s.page_id, q)}" data-go="${key}">Graph</a>${s.langs?.length ? `
      <a class="btn btn-quiet" href="/compare/${s.page_id}" title="What English and Swedish Wikipedia say that this Finnish article does not">Compare ${s.langs.map(l => l === "sv" ? "SV" : "EN").join("/")}</a>` : ""}
    </div>`;
}

function place(anchor) {
  pop.style.maxHeight = "";
  if (pop.hasAttribute("data-sheet")) { pop.style.left = pop.style.top = ""; return; }
  const w = pop.parentElement.getBoundingClientRect(), c = anchor.getBoundingClientRect();
  const pw = pop.offsetWidth, mid = c.left + c.width / 2;
  let ph = pop.offsetHeight;
  const left = Math.max(0, Math.min(mid - pw / 2 - w.left, w.width - pw));
  const roomAbove = c.top - 72 >= ph + 10, roomBelow = innerHeight - c.bottom >= ph + 10;   // 72: the sticky top bar
  // markers: above when it fits (the reader has passed that text); chips sit under the answer: below
  const above = anchor.matches(".cite") ? roomAbove || (!roomBelow && c.top > innerHeight - c.bottom) : !roomBelow && roomAbove;
  const room = above ? c.top - 72 - 10 : innerHeight - c.bottom - 10;
  if (ph > room) { pop.style.maxHeight = Math.max(160, room) + "px"; ph = pop.offsetHeight; }   // too tall for either side: it scrolls
  pop.style.left = left + "px";
  pop.style.top = (above ? c.top - w.top - ph - 10 : c.bottom - w.top + 10) + "px";
  pop.style.setProperty("--arrow", Math.max(14, Math.min(mid - w.left - left, pw - 14)) + "px");
  pop.style.transformOrigin = `${mid - w.left - left}px ${above ? "100%" : "0"}`;
  pop.dataset.side = above ? "above" : "below";
}

function setExpanded(el, on) { el?.setAttribute("aria-expanded", on ? "true" : "false"); }

// mode "peek" (preview) or "card" (dialog with the actions). animate = false for keyboard-opened
// cards and restores: keyboard actions get no motion.
function showPop(anchor, mode, animate = true) {
  const s = current?.byN.get(Number(anchor.dataset.n));
  if (!s) return;
  clearTimeout(hideTimer);
  const sheet = mode === "card" && narrow.matches;
  const same = popN === s.n && popCite === anchor && pop.dataset.mode === mode && !pop.hidden;
  if (popCite && popCite !== anchor) setExpanded(popCite, false);
  popN = s.n; popCite = anchor;
  if (!same) {
    pop.getAnimations().forEach(a => a.cancel());
    pop.dataset.mode = mode;
    pop.toggleAttribute("data-sheet", sheet);
    pop.toggleAttribute("data-era", false);
    if (s.era) pop.dataset.era = s.era;
    pop.setAttribute("role", mode === "card" ? "dialog" : "tooltip");
    pop.setAttribute("aria-label", `Source ${s.n}: ${s.title}`);
    pop.innerHTML = popHtml(s, mode === "card", claimOf(anchor));
    pop.hidden = false;
    if (mode === "peek") store.set("peekHint", 1);     // the hint is for the first preview only
  }
  place(anchor);
  setExpanded(anchor, mode === "card");
  highlight([String(s.n)]);
  scrim.hidden = !sheet;
  if (!same && animate && !reduced()) {
    if (sheet) {
      pop.animate([{ transform: "translateY(100%)" }, { transform: "none" }], { duration: 320, easing: DRAWER });
      scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: "ease" });
    } else {
      const dy = pop.dataset.side === "below" ? -4 : 4;
      pop.animate([{ opacity: 0, transform: `translateY(${dy}px) scale(${mode === "card" ? .96 : .98})` }, { opacity: 1, transform: "none" }],
                  { duration: mode === "card" ? 200 : 140, easing: EASE });
    }
  }
  if (mode === "peek") lastPeek = performance.now();
}

function closePop(animate = true, refocus = false) {
  clearTimeout(peekTimer); clearTimeout(hideTimer);
  if (pop.hidden) return;
  const anchor = popCite, sheet = pop.hasAttribute("data-sheet");
  setExpanded(anchor, false);
  popN = popCite = null;
  highlight([]);
  if (refocus) anchor?.focus();
  const done = () => { if (popN === null) { pop.hidden = true; scrim.hidden = true; } };
  if (!animate || reduced()) return done();
  pop.getAnimations().forEach(a => a.cancel());
  if (sheet) scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: "ease" });
  pop.animate(sheet ? [{ transform: "none" }, { transform: "translateY(100%)" }] : [{ opacity: 1 }, { opacity: 0, transform: "scale(.98)" }],
              { duration: sheet ? 200 : 110, easing: EASE }).finished.then(done, () => {});
}

const isCard = () => !pop.hidden && pop.dataset.mode === "card";

// hover: a short delay before the first preview, none while moving along the markers (tooltip rule)
results.addEventListener("pointerover", e => {
  const a = e.target.closest(ANCHOR);
  if (!a || !fine.matches || isCard()) return;
  clearTimeout(peekTimer); clearTimeout(hideTimer);
  const warm = performance.now() - lastPeek < 500 || !pop.hidden;
  peekTimer = setTimeout(() => showPop(a, "peek", !warm || pop.hidden), warm ? 0 : 280);
});
results.addEventListener("pointerout", e => {
  const a = e.target.closest(ANCHOR);
  if (!a || a.contains(e.relatedTarget) || isCard()) return;
  clearTimeout(peekTimer);
  if (pop.contains(e.relatedTarget)) return;            // moving into the preview keeps it
  hideTimer = setTimeout(() => closePop(), 120);
});
pop.addEventListener("pointerleave", e => {
  if (pop.dataset.mode === "peek" && !e.relatedTarget?.closest?.(ANCHOR)) hideTimer = setTimeout(() => closePop(), 120);
});
pop.addEventListener("pointerenter", () => clearTimeout(hideTimer));
// keyboard: focusing a marker previews it, Enter/Space opens the card; leaving the card closes it
results.addEventListener("focusin", e => {
  const a = e.target.closest(ANCHOR);
  if (a && a.matches(":focus-visible") && !isCard()) showPop(a, "peek", false);
});
results.addEventListener("focusout", e => {
  if (pop.dataset.mode === "peek" && e.target.closest(ANCHOR) && !pop.contains(e.relatedTarget)) closePop(false);
});
pop.addEventListener("focusout", e => {
  if (isCard() && e.relatedTarget && !pop.contains(e.relatedTarget) && e.relatedTarget !== popCite) closePop(false);
});
document.addEventListener("keydown", e => { if (e.key === "Escape" && !pop.hidden) closePop(true, true); });
document.addEventListener("pointerdown", e => {
  if (isCard() && !pop.contains(e.target) && !e.target.closest(ANCHOR)) closePop();
});
addEventListener("resize", () => { if (popCite && !pop.hidden) { pop.toggleAttribute("data-sheet", isCard() && narrow.matches); place(popCite); } });

// ---- source health and rewind: the cited passages through time ---------------------------------
// Health badges arrive after the answer (one cheap query per article). The rewind slider loads every
// year of every cited passage on first use, then scrubbing is instant: markers show whether that
// year's text was the same, different or not written yet, sentences without any source then fade,
// and an open card shows the passage as it read that year, diffed against today.
const rewindBox = $("rewind");
const NOW_YEAR = new Date().getFullYear();
let rwData = null, rwYear = null, rwIds = [], rwFor = null;
const markOp = ([op, t]) => op === "equal" ? esc(t) : op === "delete" ? `<del>${esc(t)}</del>` : `<ins>${esc(t)}</ins>`;
const rewindNote = rw => `<p class="rw-note" data-state="${rw.state}">${{
  same: `This exact text was already there at the end of ${rw.year}.`,
  changed: rw.rewritten ? `As it read at the end of ${rw.year}. Mostly rewritten since: only ${Math.round((rw.similarity || 0) * 100)}% of it is still the same today.`
    : `As it read at the end of ${rw.year}, ${Math.round((rw.similarity || 0) * 100)}% the same as today. <span class="diff-key"><del>removed since</del> <ins>added later</ins></span>`,
  absent: `Not in the article at the end of ${rw.year}. Showing today's text.`,
  no_article: `The article did not exist yet at the end of ${rw.year}. Showing today's text.`}[rw.state]}</p>`;

function refreshPop() {                                 // re-render the open preview or card in place, no motion
  if (pop.hidden || !popCite) return;
  const a = popCite, mode = pop.dataset.mode;
  popN = null;
  showPop(a, mode, false);
}

function loadHealth(res) {
  const srcs = (res.sources || []).filter(s => s.passage_id != null);
  if (!srcs.length) return;
  health(srcs.map(s => s.passage_id)).then(r => {
    if (current?.res !== res) return;                   // a newer answer took over
    for (const s of srcs) {
      s.health = r.health?.[s.passage_id];
      for (const c of results.querySelectorAll(`.src-chip[data-n="${s.n}"]`))
        c.dataset.health = !s.health ? "" : s.health.contested ? "warn" : "ok";
    }
    refreshPop();
  }).catch(() => {});                                   // badges are extra: the answer stands without them
}

function setupRewind(res) {
  rwData = null; rwYear = null; rwFor = res;
  rwIds = (res.sources || []).map(s => s.passage_id).filter(x => x != null);
  rewindBox.hidden = res.kind === "then_vs_now" || !rwIds.length;
  if (rewindBox.hidden) { rewindBox.innerHTML = ""; return; }
  rewindBox.innerHTML = `<div class="rw-head">
      <span class="kicker">Rewind the sources</span><output class="rw-year num" id="rw-year" for="rw-range">Today</output>
      <span class="rw-sum" id="rw-sum">Drag back to see each source as Wikipedia had it at the end of that year.</span></div>
    <div class="rw-track"><div class="rw-bars" id="rw-bars" aria-hidden="true"></div>
      <input type="range" id="rw-range" min="2003" max="${NOW_YEAR}" step="1" value="${NOW_YEAR}"
             aria-label="Rewind the sources to the end of a year" aria-describedby="rw-sum"></div>
    <div class="rw-ends num"><span>2003</span><a class="btn btn-quiet rw-ask" id="rw-ask" href="#" hidden></a><span>Today</span></div>`;
}

function loadRewind() {
  if (rwData || rewindBox.dataset.loading) return;
  const res = rwFor;
  rewindBox.dataset.loading = "1";
  $("rw-sum").textContent = "Reading every version of these passages…";
  rewind(rwIds).then(r => {
    if (rwFor !== res) return;
    rwData = r.passages || {};
    drawBars();
    applyYear(+$("rw-range").value);
  }).catch(e => { $("rw-sum").textContent = "The history of these passages could not be loaded: " + e.message; })
    .finally(() => delete rewindBox.dataset.loading);
}

const yearOf = (s, y) => rwData?.[s.passage_id]?.years.find(e => e.year === y);

function drawBars() {                                   // how many sources differ from today, per year
  const srcs = current.res.sources.filter(s => s.passage_id != null);
  const n = srcs.length, years = [];
  for (let y = 2003; y <= NOW_YEAR; y++) years.push([y, srcs.filter(s => (yearOf(s, y)?.state || "same") !== "same").length]);
  $("rw-bars").innerHTML = years.map(([y, k]) => `<i style="--h:${n ? k / n : 0}" title="${y}: ${k} of ${n} differ"></i>`).join("");
}

function applyYear(y) {
  rwYear = y >= NOW_YEAR ? null : y;
  $("rw-year").textContent = rwYear ?? "Today";
  const ask = $("rw-ask");
  ask.hidden = !rwYear;
  if (rwYear) {
    ask.textContent = `Ask Wikipedia as it was in ${rwYear} →`;
    ask.href = `?${new URLSearchParams({ q: current.q, as_of: `${rwYear}-12-31`, ...(mock ? { mock } : {}) })}`;
  }
  if (rwYear && !rwData) return loadRewind();
  const counts = { same: 0, changed: 0, absent: 0, no_article: 0 };
  for (const s of current.res.sources) {
    const e = rwYear && s.passage_id != null ? yearOf(s, rwYear) : null;
    const state = e?.state || "";
    if (rwYear && s.passage_id != null) counts[state || "same"]++;
    for (const m of results.querySelectorAll(`.cite[data-n="${s.n}"], .src-chip[data-n="${s.n}"]`)) m.dataset.rw = state;
    const v = e?.hash && rwData[s.passage_id].versions[e.hash];
    s.rewind = !e ? null : { year: rwYear, state, similarity: v?.similarity,
      // small edits read best as an inline diff; a mostly rewritten passage as the old text itself
      html: state === "changed" && v ? (v.similarity >= .5 ? v.ops.map(markOp).join(" ") : esc(v.text)) : null,
      rewritten: state === "changed" && v && v.similarity < .5,
      url: e.rev_id && (state === "same" || state === "changed") ? `https://fi.wikipedia.org/?oldid=${e.rev_id}` : null };
  }
  for (const sent of results.querySelectorAll(".sent[data-cites]")) {   // no source at all that year: the claim fades
    const states = sent.dataset.cites.split(" ").map(n => results.querySelector(`.cite[data-n="${n}"]`)?.dataset.rw || "");
    sent.classList.toggle("rw-gone", !!rwYear && states.every(st => st === "absent" || st === "no_article"));
  }
  const total = rwIds.length, parts = [];
  if (rwYear) {
    if (counts.changed) parts.push(`${counts.changed} read differently`);
    if (counts.absent + counts.no_article) parts.push(`${counts.absent + counts.no_article} not written yet`);
    if (counts.same) parts.push(`${counts.same} already as today`);
  }
  $("rw-sum").textContent = !rwYear ? "Drag back to see each source as Wikipedia had it at the end of that year."
    : `End of ${rwYear}: of ${total} source${total === 1 ? "" : "s"}, ${parts.join(", ")}.`;
  refreshPop();
}

rewindBox.addEventListener("input", e => { if (e.target.id === "rw-range") applyYear(+e.target.value); });
rewindBox.addEventListener("pointerdown", e => { if (e.target.id === "rw-range") loadRewind(); });   // start loading on grab
rewindBox.addEventListener("focusin", e => { if (e.target.id === "rw-range") loadRewind(); });

function renderRelated(rel, q, animate) {
  const list = rel?.articles || [];
  relatedBox.hidden = !list.length;
  relatedBox.classList.toggle("is-arriving", animate);
  relatedBox.classList.remove("is-all");
  relatedBox.innerHTML = !list.length ? "" : `<h2 class="kicker">Related articles ${sample(rel)}</h2>
    <p>Open an article's history or its graph of neighbours.</p>
    <ol class="rel-list">${list.map(a => `<li class="rel"><div>
      <h3 lang="fi"><a href="/article/${a.page_id}" data-morph="rel-${a.page_id}" data-go="rel-${a.page_id}">${esc(a.title)}</a></h3><p class="clamp" lang="fi">${esc(a.snippet)}</p></div>
      <div class="rel-actions"><a class="btn" href="${graphUrl(a.page_id, q)}" data-go="rel-${a.page_id}" aria-label="Graph of ${esc(a.title)}">${GRAPH_ICON}Graph</a></div></li>`).join("")}</ol>
    ${list.length > 4 ? `<button class="btn btn-quiet rel-more" type="button">Show all ${list.length}</button>` : ""}`;
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
  const q = input.value.trim(), date = asOf.value, id = ++run, t0 = performance.now(), scope = scopeBox?.checked ? "l" : "";
  ctrl?.abort();
  ctrl = new AbortController();
  errorBox.replaceChildren();
  if (q) { showLoading(); setState("loading"); }
  const rel = q ? related(q) : null;
  rel?.catch(() => {});                                // handled again in loadRelated; no stray rejection if ask fails
  try {
    const res = await ask(q, date || undefined, { signal: ctrl.signal, scope });
    await new Promise(r => setTimeout(r, 450 - (performance.now() - t0)));   // a very fast reply must not flash the skeleton
    if (id !== run) return;                              // a newer question took over
    setState("answer");
    render(res, q, true);
    saved = null; save({ q, asOf: date, res });
    loadHealth(res);
    const p = new URLSearchParams(location.search);     // keep the address shareable (and ?mock=1)
    p.set("q", q); date ? p.set("as_of", date) : p.delete("as_of");
    history.replaceState(null, "", "?" + p);
    document.title = q + " · Kerros";
    loadRelated(rel, q, id, true);
  } catch (e) {
    if (id !== run) return;
    stepTimers.forEach(clearTimeout);
    if (e.name === "AbortError") { setState(current ? "answer" : "landing"); if (current) render(current.res, current.q, false); return; }
    if (q) setState("error"); else input.focus();
    const limited = e.status === 429;                  // a cap on model calls, not a failure: no retry button
    errorBox.innerHTML = `<p class="alert"><span><b>${!q ? "Type a question first." : limited ? "Limit reached." : "That did not work."}</b> ${esc(e.message)}</span>
      ${q && !limited ? `<button class="btn" type="button">Try again</button>` : ""}</p>`;
  }
}

form.addEventListener("submit", e => { e.preventDefault(); submit(); });
statusBox.addEventListener("click", e => { if (e.target.closest('[data-act="cancel"]')) { run++; ctrl?.abort(); stepTimers.forEach(clearTimeout);
  results.removeAttribute("aria-busy"); if (current) { setState("answer"); render(current.res, current.q, false); } else setState("landing"); } });
errorBox.addEventListener("click", e => { if (e.target.closest("button")) submit(); });
$("examples").addEventListener("click", e => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  input.value = chip.dataset.q || chip.textContent.trim();
  asOf.value = ""; clearBtn.hidden = true;
  submit();
});
{ // the "Try one" loop: a second copy of the chips makes translateX(-50%) wrap seamlessly.
  // The copy stays clickable by mouse but is hidden from screen readers and the Tab order.
  const ul = $("examples"), qs = [...ul.querySelectorAll(".chip:not([data-q])")].map(c => c.textContent.trim());  // short ones fit the box
  for (const li of [...ul.children]) {
    const copy = li.cloneNode(true);
    copy.setAttribute("aria-hidden", "true");
    copy.querySelector("button").tabIndex = -1;
    ul.append(copy);
  }
  // the empty question box hints at a different question every few seconds
  let i = 0;
  setInterval(() => {
    if (!input.value && document.activeElement !== input) input.placeholder = qs[i++ % qs.length];
  }, 3500);
}
asOf.addEventListener("input", () => { clearBtn.hidden = !asOf.value; });
clearBtn.addEventListener("click", () => { asOf.value = ""; clearBtn.hidden = true; asOf.focus(); });

// ---- the answer's translate button (app/translate.py): sentence by sentence, citations untouched ----
answerBox.addEventListener("click", async e => {
  const b = e.target.closest(".ans-tr");
  if (!b || b.disabled) return;
  const spans = [...answerBox.querySelectorAll(".sent-t")], note = answerBox.querySelector(".ans-mt");
  if (b.dataset.orig) {                                 // back to the original
    JSON.parse(b.dataset.orig).forEach((t, k) => { spans[k].textContent = t; });
    delete b.dataset.orig;
    b.textContent = b.dataset.label;
    note.hidden = true;
    return;
  }
  const texts = spans.map(s => s.textContent);
  b.disabled = true;
  b.textContent = "Translating…";
  try {
    const r = await fetch("/api/translate", { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify({ texts, to: b.dataset.to }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.translations?.length !== texts.length) throw new Error(d.error || `HTTP ${r.status}`);
    d.translations.forEach((t, k) => { spans[k].textContent = t; });
    b.dataset.orig = JSON.stringify(texts);
    b.textContent = "Show original";
    note.hidden = false;
  } catch (err) {
    console.warn("translate answer:", err);
    b.textContent = "Translation failed, try again";
  } finally {
    b.disabled = false;
  }
});

// ---- sentence <-> marker: hover or focus one, the other lights up (paused while a source is open) ----
function highlight(ns) {
  for (const e of results.querySelectorAll(".is-hl")) e.classList.remove("is-hl");
  for (const n of ns) for (const e of results.querySelectorAll(`.cite[data-n="${n}"], .src-chip[data-n="${n}"], .sent[data-cites~="${n}"]`)) e.classList.add("is-hl");
}
const cited = t => {
  const e = t.closest?.(".cite, .src-chip, .sent");
  return !e ? [] : e.dataset.n ? [e.dataset.n] : (e.dataset.cites || "").split(" ").filter(Boolean);
};
const follow = e => { if (pop.hidden && !pop.contains(e.target)) highlight(cited(e.target)); };
results.addEventListener("pointerover", follow);
results.addEventListener("pointerleave", () => { if (pop.hidden) highlight([]); });
results.addEventListener("focusin", follow);
results.addEventListener("focusout", () => { if (pop.hidden) highlight([]); });
results.addEventListener("click", e => {
  const a = e.target.closest(ANCHOR), more = e.target.closest(".more"), go = e.target.closest("[data-go]");
  if (a) {
    clearTimeout(peekTimer);
    if (isCard() && popCite === a) closePop();
    else {
      showPop(a, "card", e.detail !== 0);
      if (e.detail === 0) pop.focus({ preventScroll: true });   // opened from the keyboard: Tab goes on to the card's links
    }
  } else if (e.target.closest(".pop-close")) closePop(true, true);
  else if (pop.dataset.mode === "peek" && pop.contains(e.target) && popCite) showPop(popCite, "card");   // the preview opens the card too
  else if (more) {
    const p = $(more.getAttribute("aria-controls"));
    p.innerHTML = p.dataset.full;                       // already escaped when the card was built
    more.remove();
    if (popCite) place(popCite);                        // the card grew: keep it clear of its marker
  } else if (go) {
    morph(go.dataset.go);
    save({ morph: go.dataset.go });
  } else if (e.target.closest(".rel-more")) {
    relatedBox.classList.add("is-all");
    e.target.closest(".rel-more").remove();
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
    loadHealth(saved.res);
    if (saved.rel) renderRelated(saved.rel, q0, false); else loadRelated(related(q0), q0, run, false);
    // back from History/Graph opened in a source card: reopen that card so its title morphs back into place
    const back = /^src-(\d+)$/.exec(saved.morph || ""), backCite = back && answerBox.querySelector(`.cite[data-n="${back[1]}"]`);
    if (backCite) showPop(backCite, "card", false);
    if (saved.morph) morph(saved.morph);
    document.title = q0 + " · Kerros";
  } else {
    asOf.value = date || "";
    root.dataset.state = "loading";                     // straight to the results layout, nothing to travel from
    submit();
  }
} else if (matchMedia("(pointer: fine)").matches) input.focus({ preventScroll: true });
clearBtn.hidden = !asOf.value;
