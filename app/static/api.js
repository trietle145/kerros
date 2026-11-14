// Data layer for every page: the live JSON route first, a fixture from ./fixtures/ when the route
// is missing (404/405), fails (5xx, network, timeout, not JSON) or the page URL has ?mock=1.
// Exception: ask() never falls back to a fixture unless ?mock=1; a failed answer shows its error.
// Every result carries _source: "live" | "fixture"; a fixture used because the live call failed
// also carries _error (why). Other 4xx (400 empty question, 422 model declined) reject with the
// JSON's error message. Call chains and backend gaps: docs/frontend-connections.md.

const FIXTURES = new URL("./fixtures/", import.meta.url);
const MOCK = new URLSearchParams(location.search).get("mock") === "1";

async function fixture(names, error) {
  for (const name of names) {                       // first one that exists (unknown page_id -> 1256)
    const r = await fetch(new URL(name, FIXTURES));
    if (r.ok) return { ...(await r.json()), _source: "fixture", ...(error && { _error: error }) };
  }
  throw new Error("No sample data: " + names.join(", "));
}

// fallback = false: a failed live call rejects instead of showing a fixture (used by ask(): a saved
// answer to a different question must never appear under the reader's question).
async function get(url, fixtures, ms = 15000, fallback = true, signal) {
  if (MOCK && fixtures.length) return fixture(fixtures);
  let r, data;
  try {
    const timeout = AbortSignal.timeout(ms);
    r = await fetch(url, { signal: signal && AbortSignal.any ? AbortSignal.any([timeout, signal]) : timeout });
    data = await r.json().catch(() => null);        // Flask's own 404/500 pages are HTML
  } catch (e) {
    if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");   // the reader pressed Cancel
    if (!fallback || !fixtures.length) throw new Error("The service did not respond (" + e.message + ")");
    return fixture(fixtures, e.message);            // server down or timeout
  }
  if (r.ok && data) return { ...data, _source: "live" };
  const message = data?.error || `HTTP ${r.status}`;
  if (!fallback || !fixtures.length || (r.status >= 400 && r.status < 500 && r.status !== 404 && r.status !== 405)) throw new Error(message);
  return fixture(fixtures, message);
}

const enc = encodeURIComponent;
const graphFixtures = (kind, pageId) => [`${kind}-${pageId}.json`, `${kind}-1256.json`];
// Which sample to show: then-vs-now when the question names a Wikipedia-era year or asks what changed.
const dated = q => /\b20[0-2]\d\b|muuttunut|changed/i.test(q || "");

// -> the /ask JSON (docs/frontend.md): {question, kind, answer, sources, [as_of, compare_to, diffs]}
// scope "l": the same answer over dataset L (all 568k Finnish articles, /ask/l)
export function ask(q, asOf, { signal, scope } = {}) {
  q = (q || "").trim();
  if (!q) return Promise.reject(new Error("q is required"));   // same text as the backend's 400
  return get(`/ask${scope === "l" ? "/l" : ""}?q=${enc(q)}${asOf ? `&as_of=${enc(asOf)}` : ""}`,
             [asOf || dated(q) ? "ask-then-vs-now.json" : "ask-plain.json"], 60000, false, signal);   // real answers take 2-17 s; fixtures only with ?mock=1
}

// -> {articles: [{page_id, title, snippet, score}]}, up to 10
export const related = q => get(`/api/related?q=${enc(q || "")}`,
                                [dated(q) ? "related-then-vs-now.json" : "related.json"]);

// -> {main, nodes, years, snapshots} (plan-graph.md); check .main, a fallback may be another article
export const graph = pageId => get(`/api/graph/${enc(pageId)}`, graphFixtures("graph", pageId));

// -> {path: [{id, why}], source: "llm" | "heuristic"}
export const path = (pageId, q) =>
  get(`/api/graph/${enc(pageId)}/path?q=${enc(q || "")}`, graphFixtures("path", pageId), 30000);

// ---- trust and editor tools (insights.py, lessons.py): live routes only, they read the database ----
const ids = list => list.filter(x => x != null).join(",");
// -> {health: {passage_id: {live_since, first_seen, rewrites, comebacks, contested}}}
export const health = passageIds => get(`/api/health?ids=${ids(passageIds)}`, [], 15000, false);
// -> {passages: {passage_id: {years: [{year, state, rev_id, hash}], versions: {hash: {text, heading, similarity, ops}}}}}
export const rewind = passageIds => get(`/api/rewind?ids=${ids(passageIds)}`, [], 30000, false);
export const find = title => get(`/api/find?title=${enc(title)}`, [], 10000, false);
export const radar = () => get("/api/radar", [], 20000, false);
export const radarPage = pageId => get(`/api/radar/${enc(pageId)}`, [], 20000, false);
export const contradictions = pageId => get(`/api/contradictions/${enc(pageId)}`, [], 30000, false);
export const cite = text => get(`/api/cite?text=${enc(text)}`, [], 30000, false);
export const explain = (pageId, revId) => get(`/api/explain/${enc(pageId)}/${enc(revId)}`, [], 30000, false);
export const lesson = (pageId, q) => get(`/api/lesson/${enc(pageId)}?q=${enc(q || "")}`, [], 60000, false);
// precomputed by tools/make_drift.py (a scan of every paragraph version takes minutes)
export const drift = () => fetch(new URL("./drift.json", import.meta.url)).then(r => r.json());
