// The graph in one year, from the /api/graph snapshots. Pure: no DOM, no fetch.
// Self-check: `node app/static/graph/time.js`, or open the graph page with ?selftest=1.

const key = ([s, t]) => s + ">" + t;

// -> exactly what g.apply takes: {visible: Set<id>, links, added, removed, revs}.
// A node is visible when it has a rev that year; added/removed compare with prevYear's links
// (both empty when prevYear is null, equal to year, or unknown).
export function stateFor(data, year, prevYear) {
  const snap = data.snapshots[year] || { revs: {}, links: [] };
  const visible = new Set(data.nodes.map(n => n.id).filter(id => id in snap.revs));
  const links = snap.links.filter(([s, t]) => visible.has(s) && visible.has(t));
  const prev = prevYear != null && prevYear != year && data.snapshots[prevYear];
  if (!prev) return { visible, links, added: [], removed: [], revs: snap.revs };
  const was = stateFor(data, prevYear, null).links;
  const now = new Set(links.map(key)), before = new Set(was.map(key));
  return {
    visible, links, revs: snap.revs,
    added: links.filter(l => !before.has(key(l))),
    // a link whose node is gone leaves with the node; only links between nodes still shown flash as removed
    removed: was.filter(l => !now.has(key(l)) && visible.has(l[0]) && visible.has(l[1])),
  };
}

// -> [{year, nodes, links}] for every year, for the sparkline and the live counts.
export function counts(data) {
  return data.years.map(year => {
    const s = stateFor(data, year, null);
    return { year, nodes: s.visible.size, links: s.links.length };
  });
}

function selftest() {
  const eq = (a, b, what) => {
    if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`time.js selftest: ${what}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
  };
  const data = {
    main: 1,
    nodes: [{ id: 1 }, { id: 2 }, { id: 3 }],
    years: [2004, 2005, 2026],
    snapshots: {
      2004: { revs: { 1: 10 }, links: [[1, 2]] },                       // 2 does not exist yet: link dropped
      2005: { revs: { 1: 11, 2: 20 }, links: [[1, 2], [2, 1]] },
      2026: { revs: { 1: 12, 2: 21, 3: 30 }, links: [[1, 2], [3, 1], [1, 9]] },   // 9 is not a node
    },
  };
  const a = stateFor(data, 2004, null);
  eq([...a.visible], [1], "2004 visible");
  eq(a.links, [], "2004 link to a node that does not exist yet");
  eq([a.added, a.removed], [[], []], "no previous year, no flashes");
  eq(a.revs, { 1: 10 }, "2004 revs");

  const b = stateFor(data, 2005, 2004);
  eq([...b.visible], [1, 2], "2005 visible");
  eq(b.added, [[1, 2], [2, 1]], "2005 added");
  eq(b.removed, [], "2005 removed");

  const c = stateFor(data, 2026, 2005);
  eq([...c.visible], [1, 2, 3], "2026 visible");
  eq(c.links, [[1, 2], [3, 1]], "2026 links");
  eq(c.added, [[3, 1]], "2026 added");
  eq(c.removed, [[2, 1]], "2026 removed (direction matters)");

  const back = stateFor(data, 2004, 2026);                              // scrubbing backwards, several years at once
  eq(back.added, [], "back added");
  eq(back.removed, [], "back removed: nodes 2 and 3 are gone in 2004, so their links leave with them");

  eq(stateFor(data, 2026, 2026).added, [], "same year, no flashes");
  eq([...stateFor(data, 1999, 2026).visible], [], "unknown year is empty");
  eq(counts(data), [{ year: 2004, nodes: 1, links: 0 }, { year: 2005, nodes: 2, links: 2 }, { year: 2026, nodes: 3, links: 2 }], "counts");
  console.log("time.js selftest ok");
}

if (typeof process !== "undefined" ? /time\.js$/.test(process.argv[1] || "") : /[?&]selftest=1/.test(location.search)) selftest();
