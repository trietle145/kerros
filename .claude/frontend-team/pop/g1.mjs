import { launch, sleep } from "../eval/cdp.mjs";
const b = await launch(9347), B = "http://127.0.0.1:5001";
await b.viewport(1440, 900);
for (const u of ["/graph/8295", "/graph/8295?mock=1"]) {
  b.log.errors.length = 0; b.log.console.length = 0; b.log.requests.length = 0; b.log.failed.length = 0;
  const t = Date.now();
  await b.go(B + u, 9000);
  console.log("\n===", u, "after", Date.now() - t, "ms");
  console.log("status:", await b.eval(`document.getElementById('graph-status')?.innerText`));
  console.log("canvas:", await b.eval(`(()=>{const c=document.querySelector('#graph-canvas canvas'); return c? c.width+'x'+c.height : 'no canvas'})()`), "| ForceGraph:", await b.eval(`typeof ForceGraph`), "| nodes list:", await b.eval(`document.querySelectorAll('#graph-nodelist button').length`), "| title:", await b.eval(`document.getElementById('graph-title')?.textContent`));
  console.log("errors:", JSON.stringify(b.log.errors));
  console.log("console:", JSON.stringify(b.log.console.slice(0,6)));
  console.log("requests:", JSON.stringify(b.log.requests.filter(x => /graph|force|fixtures|\.js/.test(x)).map(x => x.replace(B, "")).slice(0, 14)));
  console.log("failed:", JSON.stringify(b.log.failed));
  await b.shot("g1" + (u.includes("mock") ? "-mock" : ""));
}
await b.close();
