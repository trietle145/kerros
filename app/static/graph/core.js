// The graph canvas: an Obsidian-style network drawn with force-graph (global ForceGraph, loaded by
// graph.html). Knows nothing about years, panels or fetch.
//   createGraph(el, {nodes, main, links?}) -> {apply, highlightPath, focus, select, hover, on, resize, destroy}
// Positions are computed once, synchronously, by the small simulation in layout(), from all nodes
// and the links of the first apply() (pass today's; or give opts.links). Every node is then pinned
// and force-graph's own engine is off, so apply() can only show and hide: nothing that stays moves.
// All motion is a tween read in the render hooks (a pure function of time, interruptible).
// Self-check: open the page with ?selftest=1 (console, and data-selftest="ok|fail" on the container).

const TAU = Math.PI * 2, NONE = [];
const REDUCE = matchMedia("(prefers-reduced-motion: reduce)");
const SELFTEST = /[?&]selftest=1/.test(location.search);
const clamp = t => (t < 0 ? 0 : t > 1 ? 1 : t);
const cubic = t => 1 - (1 - t) ** 3;
const back = t => 1 + 1.9 * (t - 1) ** 3 + 0.9 * (t - 1) ** 2;      // ease-out with a small overshoot
const tween = v => ({ from: v, to: v, t0: 0, dur: 0, ease: cubic });
function at(a, now) {
  const t = a.dur ? (now - a.t0) / a.dur : now >= a.t0 ? 1 : 0;
  return t <= 0 ? a.from : t >= 1 ? a.to : a.from + (a.to - a.from) * a.ease(t);
}

const LABEL = 26;                       // longest label in characters; the full title shows on hover and when selected
const DIST = 120;                       // link length in graph units (= px at zoom 1)
const FLASH = { added: [220, 640], removed: [300, 420] };   // [hold, fade] ms; a year lasts 800 ms while playing

// Colours and font from the design tokens on el, normalised by a canvas ("#rrggbb" when opaque).
function tokens(el) {
  const cs = getComputedStyle(el), probe = document.createElement("canvas").getContext("2d");
  const norm = (v, fb) => { probe.fillStyle = fb; probe.fillStyle = v || fb; return probe.fillStyle; };   // a bad value keeps the fallback
  const c = (name, fb) => norm(cs.getPropertyValue(name).trim(), fb);
  let bg = c("--bg", "#0d1117");
  for (let e = el; e; e = e.parentElement) {            // what is really behind the canvas (label outlines use it)
    const b = getComputedStyle(e).backgroundColor;
    if (b && b !== "transparent" && !/,\s*0\)$/.test(b)) { bg = norm(b, bg); break; }
  }
  return {
    bg, text: c("--text", "#e6edf3"), muted: c("--muted", "#8d99a8"), accent: c("--accent", "#6ea8fe"),
    ink: c("--accent-ink", "#0b1220"), ring: c("--ring", "#ff9f43"), added: c("--added", "#3ddc84"), removed: c("--removed", "#ff6b6b"),
    rel: { main: c("--rel-main", "#ffd166"), mutual: c("--rel-mutual", "#6ea8fe"), out: c("--rel-out", "#5dd39e"),
           in: c("--rel-in", "#c792ea"), related: c("--rel-related", "#8d99a8") },
    font: cs.getPropertyValue("--font").trim() || "system-ui, -apple-system, 'Segoe UI', sans-serif",
  };
}

// Place all nodes once: link springs, repulsion, gravity (stronger in y: screens and labels are
// wide), and a label-sized box around each node so titles do not overlap. Deterministic.
// pairs: [nodeA, nodeB, length?], one per connected pair. -> the largest number of links on a node.
function layout(nodes, pairs, main) {
  const deg = new Map(nodes.map(n => [n, 0]));
  for (const [a, b] of pairs) { deg.set(a, deg.get(a) + 1); deg.set(b, deg.get(b) + 1); }
  nodes.forEach((n, i) => {
    const r = 46 * Math.sqrt(i + 0.5), t = i * 2.39996;               // sunflower start, no Math.random
    n.x = r * Math.cos(t); n.y = r * Math.sin(t); n.vx = n.vy = 0;
  });
  for (let step = 0, alpha = 1; step < 420; step++, alpha *= 0.988) {
    for (const [a, b, len = DIST] of pairs) {
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, da = deg.get(a), db = deg.get(b);
      const f = (d - len) / d * alpha * 0.9 / Math.min(da, db), bias = da / (da + db);   // the busier end moves less
      b.vx -= dx * f * bias; b.vy -= dy * f * bias;
      a.vx += dx * f * (1 - bias); a.vy += dy * f * (1 - bias);
    }
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j], dx = b.x - a.x || 0.01 * (j - i), dy = b.y - a.y || 0.01;
      const f = 1300 * alpha / (dx * dx + dy * dy);
      a.vx -= dx * f; a.vy -= dy * f; b.vx += dx * f; b.vy += dy * f;
      const ox = (a.w + b.w) / 2 - Math.abs(dx), oy = (a.h + b.h) / 2 - Math.abs(dy);   // label boxes overlap: push apart the short way
      if (ox > 0 && oy > 0) {
        if (ox < oy) { const s = Math.sign(dx) * ox * 0.25; a.x -= s; b.x += s; }
        else { const s = Math.sign(dy) * oy * 0.25; a.y -= s; b.y += s; }
      }
    }
    for (const n of nodes) {
      n.vx = (n.vx - n.x * 0.011 * alpha) * 0.6; n.vy = (n.vy - n.y * 0.034 * alpha) * 0.6;
      n.x += n.vx; n.y += n.vy;
    }
    main.x = main.y = main.vx = main.vy = 0;                           // the anchor
  }
  for (const n of nodes) { n.fx = n.x; n.fy = n.y; delete n.vx; delete n.vy; }
  return Math.max(1, ...deg.values());
}

export function createGraph(el, opts) {
  if (!window.ForceGraph) throw new Error("force-graph is not loaded");
  const C = tokens(el);
  const fade = (c, aa) => (c[0] === "#" && c.length === 7 ? c + aa : c);   // colour + alpha, for gradients

  // "Often reverted": the same rule as panel.js (at least 10 and twice the median). A pattern, not blame.
  const rv = opts.nodes.map(n => n.reverts || 0).sort((a, b) => a - b);
  const hot = Math.max(10, 2 * (rv[rv.length >> 1] || 0));

  const N = new Map(), L = new Map();                    // key -> node; "a|b" -> link (one per connected pair)
  const nodes = opts.nodes.map(d => {
    const title = d.title || String(d.id), key = String(d.id), isMain = key === String(opts.main);
    const n = {
      id: d.id, key, title, main: isMain, rel: isMain ? "main" : d.relation, ringed: (d.reverts || 0) >= hot,
      short: title.length > LABEL ? title.slice(0, LABEL - 1).trimEnd() + "…" : title,
      w: Math.min(title.length, LABEL) * 6.6 + (isMain ? 70 : 26), h: isMain ? 84 : 40,   // label box at 12 px, roughly; layout only
      on: false, delay: 0, x: 0, y: 0, fx: 0, fy: 0,
      p: tween(0), bloom: tween(1), rad: tween(5), dim: tween(0), lit: tween(0), hov: tween(0), sel: tween(0),
    };
    N.set(key, n);
    return n;
  });
  const mainNode = N.get(String(opts.main)) || nodes[0];
  let order = nodes, maxDeg = 1, laid = false, last = null, fitK = 1, userMoved = false, home = { cx: 0, cy: 0 };
  let adj = new Map(), sel = null, ptr = null, ext = null, drag = null, sticky = false;
  let pathIds = [], pathAt = new Map(), pathT = 0, busyUntil = 0, now = performance.now(), linkA = 0.4;
  const pathOn = tween(0), pathProg = tween(0);
  const handlers = { select: [], hover: [] };
  const emit = (ev, id) => handlers[ev].forEach(fn => fn(id));
  const off = new AbortController();

  const fg = ForceGraph()(el)
    .width(el.clientWidth || 800).height(el.clientHeight || 500)
    .backgroundColor("rgba(0,0,0,0)")
    .cooldownTicks(0).warmupTicks(0)                     // positions come from layout(); the engine never runs
    .minZoom(0.3).maxZoom(6)
    .nodeLabel(() => "")
    .nodeVisibility(n => n._p > 0.004)
    .nodeCanvasObject(paintNode)
    .nodePointerAreaPaint((n, color, ctx) => {           // custom-painted nodes stay hoverable and clickable
      if (!n.on) return;
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(n._x, n._y, hitR(n), 0, TAU); ctx.fill();
    })
    .onRenderFramePre(paintLinks).onRenderFramePost(paintLabels)
    .onNodeHover(n => { sticky = false; setPtr(n ? n.key : null); })
    .onNodeClick(n => { select(n.id); emit("select", n.id); })
    .onBackgroundClick(() => { if (sel) { select(null); emit("select", null); } })
    .onNodeDrag(n => {
      if (n.main) n.x = n.y = n.fx = n.fy = 0;           // the main node stays in the centre
      if (drag !== n.key) { drag = n.key; retarget(); }
      canvas.style.cursor = "grabbing";
      wake(300);
    })
    .onNodeDragEnd(n => {
      n.fx = n.x; n.fy = n.y;                            // stays where it was dropped
      drag = null; ptr = n.key; sticky = true;           // force-graph forgot the hover during the drag
      canvas.style.cursor = "pointer";
      retarget(); wake(1000);
    })
    .graphData({ nodes, links: [] });                    // links are drawn here, from our own state
  const canvas = el.querySelector("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "Network of linked articles. The same articles are in the list on this page.");
  canvas.style.cursor = "grab";

  el.addEventListener("wheel", () => { userMoved = true; }, { signal: off.signal, passive: true });
  el.addEventListener("pointerdown", () => { if (!hovered()) userMoved = true; }, { signal: off.signal });   // a pan, not a node click
  el.addEventListener("dblclick", () => { if (!hovered()) fit(600); }, { signal: off.signal });   // back to the whole graph
  el.addEventListener("pointerleave", () => {            // onto a panel or out of the window: force-graph would keep the last hover
    sticky = false;
    canvas.parentElement.dispatchEvent(new PointerEvent("pointermove", { clientX: -1e4, clientY: -1e4 }));   // tell it the pointer is nowhere
    setPtr(null);
  }, { signal: off.signal });
  el.addEventListener("pointermove", e => {              // after a drag: notice the pointer leaving the dropped node
    if (!sticky) return;
    const r = canvas.getBoundingClientRect(), g = fg.screen2GraphCoords(e.clientX - r.left, e.clientY - r.top), n = N.get(ptr);
    if (!n || Math.hypot(g.x - n.x, g.y - n.y) > hitR(n)) { sticky = false; setPtr(null); }
  }, { signal: off.signal });

  if (opts.links) place(opts.links);

  // ---- animation plumbing ------------------------------------------------------------------------
  function wake(ms) {                                    // redraw every frame for the next ms, then rest
    busyUntil = Math.max(busyUntil, performance.now() + ms + 80);
    fg.autoPauseRedraw(false);
  }
  function go(a, to, dur, delay = 0, ease = cubic) {
    if (a.to === to) return;
    const t = performance.now();
    if (REDUCE.matches) dur = delay = 0;
    a.from = at(a, t); a.to = to; a.t0 = t + delay; a.dur = dur; a.ease = ease;
    wake(delay + dur);
  }
  const hitR = n => Math.max(n._r || 0, 10 / fg.zoom()) + 2 / fg.zoom();
  const hovered = () => { const n = N.get(drag ?? ptr ?? ext); return n && n.on ? n : null; };
  function setPtr(key) {
    if (key === ptr) return;
    ptr = key;
    if (drag) return;                                    // keep the highlight while dragging
    canvas.style.cursor = key ? "pointer" : "grab";
    retarget();
    emit("hover", key ? N.get(key).id : null);
  }

  // Where every fade should end up, from the hover, the selection and the path.
  function retarget() {
    const H = hovered(), near = H && adj.get(H.key), idle = pathIds.length ? 0.62 : 0;
    for (const n of nodes) {
      const inH = H && (n === H || near?.has(n.key)), inPath = pathAt.has(n.key);
      go(n.dim, H ? (inH ? 0 : 1) : inPath ? 0 : idle, H ? 180 : 280);
      go(n.lit, H ? +!!inH : +(n.main || n === sel || inPath), 200);
      go(n.hov, +(n === H), 180);
      go(n.sel, +(n === sel), 240);
    }
    for (const l of L.values()) {
      const t = H && (l.a === H || l.b === H);
      go(l.em, t ? 1 : !H && sel && (l.a === sel || l.b === sel) ? 0.45 : 0, 200);
      go(l.dim, H ? +!t : idle, H ? 180 : 280);
    }
  }

  // ---- state -------------------------------------------------------------------------------------
  function rec(s, t) {                                   // the link between two ids, created when new
    const a = N.get(String(s)), b = N.get(String(t));
    if (!a || !b || a === b) return null;
    const fwd = a.key < b.key, key = fwd ? a.key + "|" + b.key : b.key + "|" + a.key;
    let l = L.get(key);
    if (!l) L.set(key, l = { a: fwd ? a : b, b: fwd ? b : a, ab: false, ba: false, want: false, on: false, src: a,
                             p: tween(0), em: tween(0), dim: tween(0), grow: tween(1), flash: null, ft: 0 });
    return [l, fwd];
  }

  function place(links) {                                // once: positions for all nodes
    const seen = new Set(), pairs = [];
    for (const [s, t] of links) {
      const r = rec(s, t);
      if (r && !seen.has(r[0])) { seen.add(r[0]); pairs.push([r[0].a, r[0].b, r[0].a.main || r[0].b.main ? DIST * 1.4 : DIST]); }   // room around the anchor
    }
    for (const n of nodes) if (n.rel === "related") pairs.push([mainNode, n, DIST * 1.9]);   // similar, not linked: further out
    maxDeg = layout(nodes, pairs, mainNode);
    order = [...nodes].sort((a, b) => Math.hypot(a.x, a.y) - Math.hypot(b.x, b.y));
    laid = true;
  }

  // The camera that shows the whole graph: the largest zoom, and where the main node then sits on
  // the canvas, such that no node or label is outside the canvas or under a sibling element laid
  // over it (the page floats its panel, timeline and legend on a full-size canvas).
  function frame() {
    const c = el.getBoundingClientRect(), W = c.width, H = c.height;
    const over = [];
    for (const e of el.parentElement?.children || []) {
      if (e === el) continue;
      const o = e.getBoundingClientRect();               // the element, and a positioned child that sticks out of it (a hint bubble)
      const out = [...e.querySelectorAll("*")].filter(x => x.checkVisibility?.() !== false && /absolute|fixed/.test(getComputedStyle(x).position))
        .map(x => x.getBoundingClientRect()).filter(r => r.left < o.left - 1 || r.right > o.right + 1 || r.top < o.top - 1 || r.bottom > o.bottom + 1);
      for (const r of [o, ...out]) {
        const b = [Math.max(r.left - c.left, 0), Math.max(r.top - c.top, 0), Math.min(r.right - c.left, W), Math.min(r.bottom - c.top, H)];
        if (b[2] - b[0] > 1 && b[3] - b[1] > 1) over.push(b);
      }
    }
    const search = boxes => {
      let best = null;
      const clear = (k, cx, cy) => nodes.every(n => {
        const x = cx + n.x * k, y = cy + n.y * k, l = x - n.w / 2, r = x + n.w / 2, t = y - 18, b = y + 32;   // the node and its label
        return l >= 0 && r <= W && t >= 0 && b <= H && !boxes.some(B => B[0] < r && B[2] > l && B[1] < b && B[3] > t);
      });
      for (let i = 1; i < 20; i++) for (let j = 1; j < 20; j++) {
        const cx = W * i / 20, cy = H * j / 20, d = Math.hypot(cx - W / 2, cy - H / 2);
        for (let k = 1.8; k >= (best ? best.k : 0.3); k -= 0.04) {
          if (!clear(k, cx, cy)) continue;
          if (!best || k > best.k + 1e-9 || d < best.d) best = { k, cx, cy, d };
          break;
        }
      }
      return best;
    };
    return search(over) || search([]) || { k: 0.3, cx: W / 2, cy: H / 2 };
  }

  function aim(x, y, k, ms) {                            // graph point (x, y) to where the main node sits at home
    if (REDUCE.matches) ms = 0;
    fg.centerAt(x - (home.cx - el.clientWidth / 2) / k, y - (home.cy - el.clientHeight / 2) / k, ms).zoom(k, ms);
    wake(ms + 200);
  }

  function fit(ms) {                                     // back home: the whole graph in view
    if (!el.clientWidth || !el.clientHeight) return;
    home = frame();
    fitK = home.k === 1 ? 1.001 : home.k;                // force-graph re-zooms by itself when zoom is exactly its last own value (1)
    userMoved = false;
    aim(0, 0, fitK, ms);
  }

  function apply(s) {
    const first = !last, vis = new Set([...s.visible].map(String));
    last = s;
    for (const l of L.values()) l.want = false;
    const want = (s0, t0) => {
      const r = rec(s0, t0);
      if (!r) return;
      const [l, fwd] = r;
      if (!l.want) { l.want = true; l.ab = l.ba = false; }
      l[fwd ? "ab" : "ba"] = true;
    };
    if (!laid) place(s.links);
    for (const [s0, t0] of s.links) want(s0, t0);
    for (const n of nodes) {                             // similar by topic, not linked: a dashed line to the main node
      if (n.rel === "related") { const r = rec(mainNode.id, n.id); if (r && !r[0].want) { r[0].want = true; r[0].ab = r[0].ba = false; } }
    }

    let k = 0;
    for (const n of order) {
      const on = vis.has(n.key);
      n.delay = 0;
      if (on && !n.on) {
        n.delay = first ? 60 + k++ * 34 : Math.min(k++ * 45, 315);
        if (first && !REDUCE.matches) { n.bloom = tween(0); go(n.bloom, 1, 950, n.delay, back); }   // bloom out from the centre
        go(n.p, 1, first ? 650 : 480, n.delay, back);
      } else if (!on && n.on) go(n.p, 0, 280);
      n.on = on;
    }

    const gone = new Set(), born = new Map();
    if (!first) {
      for (const [s0, t0] of s.removed || []) { const r = rec(s0, t0); if (r) gone.add(r[0]); }
      for (const [s0, t0] of s.added || []) { const r = rec(s0, t0); if (r && !born.has(r[0])) born.set(r[0], N.get(String(s0))); }
    }
    const t = performance.now(), flash = (l, kind, delay) => { l.flash = kind; l.ft = t + delay; wake(delay + FLASH[kind][0] + FLASH[kind][1]); };
    for (const l of L.values()) {
      const on = l.want && l.a.on && l.b.on, enter = Math.max(l.a.delay, l.b.delay);
      const delay = first ? enter + 320 : l.a.delay || l.b.delay ? enter + 200 : 0;
      if (on && !l.on) {
        go(l.p, 1, born.has(l) ? 120 : 380, delay);
        if (born.has(l) && !REDUCE.matches) { l.src = born.get(l); l.grow = tween(0); go(l.grow, 1, 420, delay); }   // drawn from its source
      } else if (!on && l.on) go(l.p, 0, gone.has(l) ? FLASH.removed[1] : 280, gone.has(l) ? FLASH.removed[0] : 0);
      if (born.has(l) && on) flash(l, "added", delay);
      else if (gone.has(l) && l.on) flash(l, "removed", 0);   // also when only one direction went away
      l.on = on;
    }

    adj = new Map(nodes.map(n => [n.key, new Set()]));
    for (const l of L.values()) if (l.on && (l.ab || l.ba)) { adj.get(l.a.key).add(l.b.key); adj.get(l.b.key).add(l.a.key); }
    for (const n of nodes) {                             // size = links inside the graph, in the state shown
      const d = Math.min(1.2, adj.get(n.key).size / maxDeg);
      go(n.rad, n.main ? 10 + 5 * Math.sqrt(d) : 4.5 + 7 * Math.sqrt(d), 420);
    }
    linkA = Math.max(0.26, 0.5 - 0.0035 * [...L.values()].filter(l => l.on).length);   // many links: each one fainter
    retarget();
    wake(1000);                                          // long enough for force-graph to refresh its hit map
    if (first) {
      fit(0);
      if (!REDUCE.matches) fg.zoom(fitK * 0.86).zoom(fitK, 1300);   // ease in while the nodes bloom
      if (SELFTEST) setTimeout(selftest, 2600);
    }
  }

  function select(id) {
    sel = id == null ? null : N.get(String(id)) || null;
    retarget();
  }

  function highlightPath(ids) {
    const keys = (ids || []).map(String).filter(k => N.has(k));
    if (keys.length) {
      pathIds = keys; pathAt = new Map(keys.map((k, i) => [k, i]));
      pathT = performance.now() + keys.length * 240 + 500;             // when the travelling dot starts
      Object.assign(pathProg, tween(0));
      go(pathProg, keys.length, keys.length * 240, 120, t => t);   // badges pop and connectors draw in reading order
      go(pathOn, 1, 200);
    } else {
      pathAt = new Map();                                // the drawing fades out; pathIds stays until then
      go(pathOn, 0, 260);
      setTimeout(() => { if (pathOn.to === 0) pathIds = []; }, 300);
    }
    retarget();
  }

  function focus(id) {
    const n = N.get(String(id));
    if (!n) return;
    userMoved = true;
    aim(n.x, n.y, Math.max(fg.zoom(), Math.min(2.2, fitK * 1.35)), 700);
  }

  // ---- painting (graph units; divide by k for sizes that should not grow with zoom) ----------------
  function paintLinks(ctx, k) {
    now = performance.now();
    for (const n of nodes) {
      const p = at(n.p, now), b = at(n.bloom, now);
      n._p = p; n._a = clamp(p) * (1 - 0.84 * at(n.dim, now));
      n._x = n.x * b; n._y = n.y * b;
      n._r = at(n.rad, now) * Math.max(0, p) * (1 + 0.18 * at(n.hov, now));
    }
    ctx.lineCap = "round";
    for (const l of L.values()) {
      const A = l.a, B = l.b, p = at(l.p, now) * Math.min(1, A._p, B._p);
      if (p < 0.01) continue;
      const dx = B._x - A._x, dy = B._y - A._y, d = Math.hypot(dx, dy), gap = 2.5 / k;
      if (d < A._r + B._r + 3 * gap) continue;
      const ux = dx / d, uy = dy / d, gr = at(l.grow, now);
      let x1 = A._x + ux * (A._r + gap), y1 = A._y + uy * (A._r + gap), x2 = B._x - ux * (B._r + gap), y2 = B._y - uy * (B._r + gap);
      if (gr < 1) {
        if (l.src === A) { x2 = x1 + (x2 - x1) * gr; y2 = y1 + (y2 - y1) * gr; }
        else { x1 = x2 + (x1 - x2) * gr; y1 = y2 + (y1 - y2) * gr; }
      }
      // one-way links get a small arrowhead at their target; both ways (and "related") get none
      const head = gr >= 1 && l.ab !== l.ba ? Math.min(5.5, 10 / k) : 0, toB = l.ab;
      const hx = toB ? x2 : x1, hy = toB ? y2 : y1, sx = toB ? ux : -ux, sy = toB ? uy : -uy;
      if (head) { if (toB) { x2 -= ux * head * 0.8; y2 -= uy * head * 0.8; } else { x1 += ux * head * 0.8; y1 += uy * head * 0.8; } }
      const draw = (colour, alpha, width) => {
        if (alpha < 0.012) return;
        ctx.globalAlpha = Math.min(1, alpha); ctx.strokeStyle = ctx.fillStyle = colour; ctx.lineWidth = width / k;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        if (head) {
          ctx.beginPath(); ctx.moveTo(hx, hy);
          ctx.lineTo(hx - sx * head - sy * head * 0.42, hy - sy * head + sx * head * 0.42);
          ctx.lineTo(hx - sx * head + sy * head * 0.42, hy - sy * head - sx * head * 0.42);
          ctx.fill();
        }
      };
      let f = 0;
      if (l.flash) {
        const [hold, fadeMs] = FLASH[l.flash], e = now - l.ft;
        if (e > hold + fadeMs) l.flash = null;
        else if (e >= 0) f = e < hold ? 1 : 1 - (REDUCE.matches ? 1 : cubic((e - hold) / fadeMs));
      }
      const em = at(l.em, now), dim = at(l.dim, now);
      ctx.setLineDash(!(l.ab || l.ba) || A.rel === "related" || B.rel === "related" ? [3 / k, 4.5 / k] : NONE);
      draw(C.muted, p * linkA * (1 - 0.82 * dim) * (1 - em) * (1 - f), 1);
      draw(C.text, p * 0.85 * em * (1 - f), 1.4);
      draw(l.flash === "removed" ? C.removed : C.added, p * f, 1.1 + 1.2 * f);
    }

    // learning path: connectors in reading order, solid where a real link exists, dotted otherwise
    const po = at(pathOn, now);
    if (po > 0.01 && pathIds.length > 1) {
      const prog = at(pathProg, now), segs = pathIds.length - 1;
      const seg = i => {
        const A = N.get(pathIds[i]), B = N.get(pathIds[i + 1]), dx = B._x - A._x, dy = B._y - A._y, d = Math.hypot(dx, dy) || 1;
        return { A, B, ux: dx / d, uy: dy / d, len: Math.max(0, d - A._r - B._r - 9 / k), a: po * Math.min(1, A._p, B._p) };
      };
      ctx.strokeStyle = ctx.fillStyle = C.accent; ctx.lineWidth = 2 / k;
      for (let i = 0; i < segs; i++) {
        const { A, B, ux, uy, len, a } = seg(i), g = cubic(clamp(prog - i - 0.5));
        if (a < 0.01 || g <= 0 || !len) continue;
        const x1 = A._x + ux * (A._r + 4 / k), y1 = A._y + uy * (A._r + 4 / k), x2 = x1 + ux * len * g, y2 = y1 + uy * len * g;
        const real = adj.get(A.key)?.has(B.key), h = 7 / k;
        ctx.globalAlpha = a * (real ? 0.95 : 0.8);
        ctx.setLineDash(real ? NONE : [0.1, 5 / k]);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2 - ux * h * 0.6, y2 - uy * h * 0.6); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x2, y2);                           // arrowhead: the reading direction
        ctx.lineTo(x2 - ux * h - uy * h * 0.5, y2 - uy * h + ux * h * 0.5);
        ctx.lineTo(x2 - ux * h + uy * h * 0.5, y2 - uy * h - ux * h * 0.5);
        ctx.fill();
      }
      ctx.setLineDash(NONE);
      if (!REDUCE.matches && now >= pathT) {                           // one dot travels the path, pauses, starts again
        const T = ((now - pathT) / 1000) % (segs + 1.6), i = Math.floor(T);
        if (i < segs) {
          const { A, ux, uy, len, a } = seg(i), u = T - i, e = u * u * (3 - 2 * u);
          const x = A._x + ux * (A._r + 4 / k + len * e), y = A._y + uy * (A._r + 4 / k + len * e);
          ctx.fillStyle = C.text;
          ctx.globalAlpha = a * 0.25; ctx.beginPath(); ctx.arc(x, y, 7 / k, 0, TAU); ctx.fill();
          ctx.globalAlpha = a; ctx.beginPath(); ctx.arc(x, y, 2.8 / k, 0, TAU); ctx.fill();
        }
      }
    }
    ctx.setLineDash(NONE);
    ctx.globalAlpha = 1;
  }

  function paintNode(n, ctx, k) {
    const a = n._a, r = n._r, x = n._x, y = n._y, c = C.rel[n.rel] || C.rel.related;
    if (a < 0.004 || r <= 0) return;
    const circle = rr => { ctx.beginPath(); ctx.arc(x, y, rr, 0, TAU); };
    const glow = Math.max(at(n.hov, now), at(n.sel, now));
    if (n.main) {                                        // the anchor: a soft halo
      const g = ctx.createRadialGradient(x, y, r * 0.8, x, y, r * 3.4);
      g.addColorStop(0, fade(c, "50")); g.addColorStop(1, fade(c, "00"));
      ctx.globalAlpha = c[0] === "#" ? a : a * 0.15; ctx.fillStyle = g; circle(r * 3.4); ctx.fill();
    }
    if (glow > 0.01) { ctx.globalAlpha = a * 0.22 * glow; ctx.fillStyle = c; circle(r + 7 / k); ctx.fill(); }
    ctx.globalAlpha = a;
    if (n.rel === "related") {                           // hollow, like its dot in the legend: not linked
      ctx.fillStyle = C.bg; circle(r); ctx.fill();
      ctx.strokeStyle = c; ctx.lineWidth = Math.min(2 / k, r * 0.5); circle(r - ctx.lineWidth / 2); ctx.stroke();
    } else { ctx.fillStyle = c; circle(r); ctx.fill(); }
    if (n.ringed) { ctx.strokeStyle = C.ring; ctx.lineWidth = 1.4 / k; circle(r + 3.6 / k); ctx.stroke(); }   // often reverted
    const s = at(n.sel, now);
    if (s > 0.01) { ctx.globalAlpha = a * s; ctx.strokeStyle = C.text; ctx.lineWidth = 2 / k; circle(r + 0.6 / k); ctx.stroke(); }
    ctx.globalAlpha = 1;
  }

  function paintLabels(ctx, k) {
    const zoomA = clamp((k - 0.42) / 0.22);              // labels fade in with zoom; lit ones always show
    ctx.textAlign = "center"; ctx.lineJoin = "round"; ctx.strokeStyle = C.bg; ctx.fillStyle = C.text;
    const H = hovered();
    const label = n => {
      const lit = at(n.lit, now), a = clamp(n._p) * clamp(at(n.bloom, now)) ** 4 * Math.max(lit, zoomA * (1 - at(n.dim, now)));
      if (a < 0.02) return;
      ctx.font = `${n.main ? 600 : 400} ${(n.main ? 13.5 : 12) / k}px ${C.font}`;
      const text = n === H || n === sel ? n.title : n.short, ty = n._y + n._r + (n.ringed ? 8 : 5) / k;
      ctx.textBaseline = "top";
      ctx.globalAlpha = a * 0.85; ctx.lineWidth = 3 / k; ctx.strokeText(text, n._x, ty);
      ctx.globalAlpha = a * (0.72 + 0.28 * lit); ctx.fillText(text, n._x, ty);
    };
    for (const n of nodes) if (n !== H) label(n);
    if (H) label(H);                                     // the hovered title on top

    const po = at(pathOn, now);
    if (po > 0.01) {
      const prog = at(pathProg, now);
      ctx.textBaseline = "middle";
      pathIds.forEach((key, i) => {                      // numbered badges, popping in reading order
        const n = N.get(key), s = back(clamp(prog - i)) * po * clamp(n._p);
        if (s < 0.02) return;
        const R = 9 / k * s, o = (n._r + 5 / k) * 0.72, x = n._x + o, y = n._y - o;
        ctx.globalAlpha = clamp(s);
        ctx.fillStyle = C.accent; ctx.beginPath(); ctx.arc(x, y, R, 0, TAU); ctx.fill();
        ctx.lineWidth = 1.5 / k; ctx.strokeStyle = C.bg; ctx.stroke();
        ctx.fillStyle = C.ink; ctx.font = `700 ${11 * s / k}px ${C.font}`;
        ctx.fillText(i + 1, x, y + 0.5 / k);
      });
      ctx.fillStyle = C.text; ctx.strokeStyle = C.bg;
    }
    ctx.globalAlpha = 1;
    const loop = pathIds.length > 1 && pathOn.to === 1 && !REDUCE.matches;   // the travelling dot
    if (now > busyUntil && !loop) fg.autoPauseRedraw(true);                  // nothing is moving: stop redrawing
  }

  // ---- self-check: apply() with fewer nodes must not move anything ---------------------------------
  function selftest() {
    const pos = () => nodes.map(n => [n.x, n.y, n.fx, n.fy].join()).join(";");
    const before = pos(), full = last, half = new Set([...full.visible].filter((_, i) => i % 2 === 0));
    const both = ([s, t]) => half.has(s) && half.has(t);
    const fails = [];
    const check = (ok, what) => { if (!ok) fails.push(what); };
    apply({ visible: half, links: full.links.filter(both), added: [], removed: full.links.filter(l => !both(l)), revs: full.revs });
    check(nodes.every(n => n.on === half.has(n.id)), "apply shows exactly the visible set");
    setTimeout(() => {
      check(pos() === before, "nodes moved after apply with fewer nodes");
      check(nodes.every(n => n.on || n._p < 0.01), "hidden nodes are still drawn");
      apply({ ...full, added: full.links.filter(l => !both(l)), removed: [] });
      setTimeout(() => {
        check(pos() === before, "nodes moved after showing everything again");
        check(nodes.every(n => !n.on || (Math.abs(n._x - n.x) < 1e-6 && Math.abs(n._y - n.y) < 1e-6 && Math.abs(n._p - 1) < 1e-6)), "visible nodes are not drawn at rest in their own position");
        check(mainNode.x === 0 && mainNode.y === 0, "the main node left the centre");
        el.dataset.selftest = fails.length ? "fail" : "ok";
        console[fails.length ? "error" : "info"]("core.js selftest " + (fails.length ? "FAILED: " + fails.join("; ") : "ok"));
      }, 1200);
    }, 1200);
  }
  if (SELFTEST) el._graph = { fg, nodes, links: L };     // for tests only

  return {
    apply, highlightPath, focus, select,
    hover(id) { ext = id == null ? null : String(id); retarget(); },   // highlight from outside (the list); no event
    on(ev, fn) { handlers[ev]?.push(fn); },
    resize() {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h || (w === fg.width() && h === fg.height())) return;
      fg.width(w).height(h);
      if (!userMoved && laid) fit(0);
      wake(300);
    },
    destroy() {
      off.abort();
      fg._destructor();
      (canvas.closest(".force-graph-container") || canvas).remove();
    },
  };
}
