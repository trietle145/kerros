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
async function get(url, fixtures, ms = 15000, fallback = true) {
  if (MOCK) return fixture(fixtures);
  let r, data;
  try {
    r = await fetch(url, { signal: AbortSignal.timeout(ms) });
    data = await r.json().catch(() => null);        // Flask's own 404/500 pages are HTML
  } catch (e) {
    if (!fallback) throw new Error("The answer service did not respond (" + e.message + ")");
    return fixture(fixtures, e.message);            // server down or timeout
  }
  if (r.ok && data) return { ...data, _source: "live" };
  const message = data?.error || `HTTP ${r.status}`;
  if (!fallback || (r.status >= 400 && r.status < 500 && r.status !== 404 && r.status !== 405)) throw new Error(message);
  return fixture(fixtures, message);
}

const enc = encodeURIComponent;
const graphFixtures = (kind, pageId) => [`${kind}-${pageId}.json`, `${kind}-1256.json`];
// Which sample to show: then-vs-now when the question names a Wikipedia-era year or asks what changed.
const dated = q => /\b20[0-2]\d\b|muuttunut|changed/i.test(q || "");

// -> the /ask JSON (docs/frontend.md): {question, kind, answer, sources, [as_of, compare_to, diffs]}
export function ask(q, asOf) {
  q = (q || "").trim();
  if (!q) return Promise.reject(new Error("q is required"));   // same text as the backend's 400
  return get(`/ask?q=${enc(q)}${asOf ? `&as_of=${enc(asOf)}` : ""}`,
             [asOf || dated(q) ? "ask-then-vs-now.json" : "ask-plain.json"], 60000, false);   // real answers take 2-17 s; fixtures only with ?mock=1
}

// -> {articles: [{page_id, title, snippet, score}]}, up to 10
export const related = q => get(`/api/related?q=${enc(q || "")}`,
                                [dated(q) ? "related-then-vs-now.json" : "related.json"]);

// -> {main, nodes, years, snapshots} (plan-graph.md); check .main, a fallback may be another article
export const graph = pageId => get(`/api/graph/${enc(pageId)}`, graphFixtures("graph", pageId));

// -> {path: [{id, why}], source: "llm" | "heuristic"}
export const path = (pageId, q) =>
  get(`/api/graph/${enc(pageId)}/path?q=${enc(q || "")}`, graphFixtures("path", pageId), 30000);
