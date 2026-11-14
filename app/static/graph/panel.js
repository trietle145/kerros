// The side panel of the graph page: the selected article, the empty state and the learning path.
// All Wikipedia text goes in through textContent (el), never innerHTML.

export const REL = {
  main:    { label: "Main article",     words: "The main article of this graph" },
  mutual:  { label: "Linked both ways", words: "Links to and from the main article" },
  out:     { label: "Linked from main", words: "The main article links to it" },
  in:      { label: "Links to main",    words: "Links to the main article" },
  related: { label: "Related by topic", words: "Related by topic, no direct link to the main article" },
};

export const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// el("a.g-btn", {href}, "text", node, ...) -> element; null/false children are skipped.
export function el(spec, attrs, ...kids) {
  const [tag, ...cls] = spec.split(".");
  const e = document.createElement(tag || "div");
  if (cls.length) e.className = cls.join(" ");
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v != null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  e.append(...kids.flat().filter(k => k != null && k !== false));
  return e;
}

export const dot = rel => el("span.g-dot.g-rel-" + rel, { "aria-hidden": "true" });
const wiki = rev => "https://fi.wikipedia.org/?oldid=" + rev;

// shortcut: only the leftover image markup seen in the data ("thumb|325px|caption…} Real lead"); the
// real fix is in the backend's lead text.
export function cleanLead(s = "") {
  if (!/^\s*thumb\|/.test(s)) return s;
  const end = s.indexOf("}", s.lastIndexOf("thumb|"));
  return (end > 0 ? s.slice(end + 1) : s.replace(/thumb\|(?:[^|\s]*\|)*/g, " ")).trim();
}

// Ids whose revert count is high next to the other nodes: at least 10 and twice the median.
export function oftenReverted(nodes) {
  const r = nodes.map(n => n.reverts || 0).sort((a, b) => a - b);
  const limit = Math.max(10, 2 * r[r.length >> 1]);
  return new Set(nodes.filter(n => (n.reverts || 0) >= limit).map(n => n.id));
}

// createPanel(root, {data, q, graphUrl, select}) -> {show(node | null), setYear(year)}
//   select(id): select a node and centre it; graphUrl(id): the graph page with that node as main.
export function createPanel(root, { data, g, q, api, graphUrl, select }) {
  const byId = new Map(data.nodes.map(n => [n.id, n]));
  const main = byId.get(data.main);
  const hot = oftenReverted(data.nodes);
  const lastYear = data.years[data.years.length - 1];
  let year = lastYear, node = null, yearly = null;      // yearly(): refresh the parts that depend on the year
  let markPath = () => {};

  const body = el("div.gp-body");
  const say = el("p.g-sr", { "aria-live": "polite" });  // one short line for screen readers, not the whole panel
  root.replaceChildren(el("div.gp", null, body, say, pathSection()));
  swap(emptyView());

  function swap(view) {                                 // crossfade: the old view fades out on top, the new one slides in
    const old = body.lastElementChild;
    if (old && !reduced()) {
      old.classList.add("is-leaving");
      old.addEventListener("animationend", () => old.remove(), { once: true });
      setTimeout(() => old.remove(), 400);              // animationend never fires in a hidden tab
    } else old?.remove();
    body.append(view);
  }

  function emptyView() {
    const others = data.nodes.length - 1;
    return el("div.gp-view.gp-empty", null,
      el("h2", null, "How these articles connect"),
      el("p", null,
        el("span.gp-long", null, el("strong", { lang: "fi" }, main?.title || "The main article"),
          ` and the ${others} Wikipedia article${others === 1 ? "" : "s"} closest to it. Each line is a link from one article to another: `),
        el("span.gp-pitch", null, "explore how the sources connect, and how those connections grew.")),
      el("p.gp-tip", null, "Select an article to read about it, or press play to travel through the years."));
  }

  function nodeView(n) {
    const absent = el("p.gp-absent", { hidden: true });
    const open = el("a.g-btn.g-btn-primary", { target: "_blank", rel: "noopener" });
    const history = el("a.g-btn", null, "History");
    const credit = el("p.gp-credit", { hidden: true }, "Lead text from ",
      el("a", { href: wiki(n.rev_id), target: "_blank", rel: "noopener" }, "the current version"), ".");
    const text = cleanLead(n.lead);
    const lead = el("p.gp-lead", { lang: "fi" }, text);
    const more = el("button.g-link.gp-more", { type: "button", hidden: true, "aria-expanded": "false", onclick() {
      const openNow = lead.classList.toggle("is-open");
      more.textContent = openNow ? "Show less" : "Show more";
      more.setAttribute("aria-expanded", openNow);
    } }, "Show more");

    yearly = () => {
      const rev = data.snapshots[year]?.revs[n.id];
      const past = year !== lastYear;
      absent.hidden = !!rev;
      absent.textContent = rev ? "" : `Not written yet in ${year}. Its first version is from ${n.created}.`;
      open.hidden = !rev;
      open.href = wiki(rev || n.rev_id);
      open.replaceChildren("Open on Wikipedia", past ? el("span.gp-ver", null, ` · ${year} version`) : "", el("span", { "aria-hidden": "true" }, " ↗"));
      history.href = `/article/${n.id}` + (past && rev ? `?as_of=${year}-12-31` : "");
      credit.hidden = !text || rev === n.rev_id;   // the lead is today's text, so name its own version (CC BY-SA)
    };
    yearly();

    const view = el("article.gp-view.gp-node", { "aria-labelledby": "gp-title" },
      el("p.gp-rel", null, dot(n.relation), (REL[n.relation] || REL.related).words),
      el("h2", { id: "gp-title", lang: "fi" }, n.title),
      el("p.gp-meta", null,
        n.created && el("span", null, `First version ${n.created}`),
        hot.has(n.id) && el("span.gp-badge", { title: `${n.reverts} edits to this article were undone. A pattern in its history, not a judgement.` },
          el("span.g-ring", { "aria-hidden": "true" }), "often reverted")),
      absent,
      text && lead, more, credit,
      el("div.gp-actions", null, open, history,
        /^https:\/\//.test(n.other_langs?.en?.url || "") && el("a.g-btn", { href: n.other_langs.en.url, target: "_blank",
          rel: "noopener", lang: "en", title: `The same topic on English Wikipedia: ${n.other_langs.en.title}` }, "English Wikipedia ↗"),
        n.id !== data.main && el("a.g-btn", { href: graphUrl(n.id) }, "Make this the main node")));
    // the "Show more" button only when the clamped lead really overflows (needs layout first)
    requestAnimationFrame(() => { more.hidden = lead.scrollHeight <= lead.clientHeight + 2; });
    return view;
  }

  // ---- learning path -------------------------------------------------------------------------
  function pathSection() {
    const go = el("button.g-btn.gp-path-go", { type: "button", onclick: load }, "Suggest a reading order");
    const ASK = "In which order should you read these articles?";
    const what = el("p.gp-path-what", null, ASK);         // the question, then where the order came from
    const clear = el("button.g-link", { type: "button", hidden: true, onclick: reset }, "Clear");
    const out = el("div.gp-path-out", { "aria-live": "polite" });
    let steps = [];

    function reset() {
      steps = [];
      g.highlightPath(null);
      out.replaceChildren(); what.textContent = ASK; clear.hidden = true; go.hidden = false;
      go.focus();
    }

    async function load() {
      go.hidden = true;
      out.replaceChildren(el("p.gp-path-wait", null, el("span.g-spin", { "aria-hidden": "true" }), "Finding a reading order…"));
      let res;
      try {
        res = await api.path(data.main, q);
      } catch (e) {
        go.hidden = false;
        out.replaceChildren(el("p.gp-path-err", null, "No reading order right now. Please try again."));
        console.warn("learning path:", e);
        return;
      }
      steps = (res.path || []).filter(s => byId.has(s.id));         // only nodes that are shown
      if (!steps.length) {
        go.hidden = false;
        return out.replaceChildren(el("p.gp-path-err", null, "No reading order for these articles."));
      }
      g.highlightPath(steps.map(s => s.id));
      what.textContent = (res.source === "llm" ? "Reading order chosen by the language model" : "Suggested order (heuristic)")
        + (res._source === "fixture" ? ", sample data" : "");
      clear.hidden = false;
      out.replaceChildren(el("ol.gp-steps", null, steps.map((s, i) =>
        el("li", { style: `--i:${i}` }, el("button", { type: "button", "data-id": s.id, onclick: () => select(s.id) },
          el("span.gp-n", { "aria-hidden": "true" }, i + 1),
          el("span.gp-step-t", { lang: "fi" }, byId.get(s.id).title),
          el("span.gp-why", null, s.why || ""))))));
      mark();
    }

    // which step is the selected node, and which steps do not exist in the year shown
    function mark() {
      for (const b of out.querySelectorAll("button[data-id]")) {
        const id = +b.dataset.id;
        b.classList.toggle("is-current", node?.id === id);
        const absent = !data.snapshots[year]?.revs[id];
        b.classList.toggle("is-absent", absent);
        b.title = absent ? `Not written yet in ${year}` : "";
      }
    }
    markPath = mark;

    return el("section.gp-path", { "aria-label": "Learning path" },
      el("div.gp-path-head", null, el("h3", null, "Learning path"), clear), what, go, out);
  }

  return {
    show(n) {
      if (n === node) return;
      node = n; yearly = null;
      swap(n ? nodeView(n) : emptyView());
      say.textContent = n ? `${n.title}: ${(REL[n.relation] || REL.related).words}` : "";
      markPath();
    },
    setYear(y) {
      year = y;
      yearly?.();
      markPath();
    },
  };
}
