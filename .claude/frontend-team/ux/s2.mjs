import { launch, sleep } from "../eval/cdp.mjs";
import { writeFileSync } from "node:fs";
const D = "C:/Users/hvhun/junction_hackathon/.claude/frontend-team/ux/shots";
const b = await launch(9352), B = "http://127.0.0.1:5006";
const shot = async n => { const r = await b.send("Page.captureScreenshot", { format: "png" }); writeFileSync(`${D}/${n}.png`, Buffer.from(r.data, "base64")); };
const full = async n => { const r = await b.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true }); writeFileSync(`${D}/${n}.png`, Buffer.from(r.data, "base64")); };
const out = []; const log = (...a) => out.push(a.join(" "));
const PLAIN = B + "/?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi?");
const TVN = B + "/?mock=1&q=" + encodeURIComponent("Mitä Wikipedia sanoi punavangeista vuonna 2007, ja mitä on muuttunut?");
// graph 1440
await b.viewport(1440, 900);
await b.go(B + "/graph/1256?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi?"), 4000); await shot("20-graph-1256");
log("graph panel", (await b.eval(`document.getElementById('graph-panel').innerText`)).slice(0,700));
log("graph timeline", (await b.eval(`document.getElementById('graph-timeline').innerText`)).slice(0,300));
log("graph legend", await b.eval(`document.getElementById('graph-legend').innerText`));
log("graph status", await b.eval(`document.getElementById('graph-status').innerText`));
log("focusables", await b.eval(`[...document.querySelectorAll('#graph-panel button,#graph-panel a,#graph-timeline button,#graph-timeline input,#graph-nodelist button')].length`));
// play slider
const play = await b.eval(`(()=>{const p=[...document.querySelectorAll('#graph-timeline button')][0]; if(!p) return null; p.click(); return p.textContent+'|'+p.getAttribute('aria-label')})()`); log("play", play);
await sleep(1500); await shot("21-graph-playing");
await b.viewport(1920, 1080); await b.go(B + "/graph/8295?mock=1&q=x", 4000); await shot("22-graph-8295-1920");
await b.go(B + "/graph/1150?mock=1&q=x", 4000); await shot("23-graph-1150-1440"); 
// history
await b.viewport(1440, 900);
await b.go(B + "/article/1256", 2500); await shot("30-history-1440"); await full("31-history-full");
log("history head", await b.eval(`document.querySelector('.hist-head')?.innerText`));
log("history links", await b.eval(`[...document.querySelectorAll('.version a')].map(a=>a.href).join(' ')`));
await b.go(B + "/article/1256?as_of=2007-06-01", 2500); await shot("32-history-2007");
// transitions: plain answer -> click card Graph, capture frames
await b.go(PLAIN, 2000);
let r = await b.rect('.cite[data-n="1"]'); await b.click(r.x, r.y); await sleep(300);
r = await b.eval(`(()=>{const a=[...document.querySelectorAll('#cite-pop a')].find(a=>a.textContent.trim()==='History').getBoundingClientRect(); return {x:a.x+a.width/2,y:a.y+a.height/2}})()`);
await b.click(r.x, r.y);
for (const t of [0,100,200,400]) { await sleep(t===0?0:t===400?200:100); await shot(`40-to-history-${t}ms`); }
await sleep(1500); log("history url", await b.eval(`location.href`)); await shot("41-history-arrived");
log("back link", await b.eval(`document.getElementById('back-q')?.href`));
await b.send("Page.navigateToHistoryEntry", { entryId: (await b.send("Page.getNavigationHistory")).entries.at(-2).id });
for (const t of [0,100,200,400]) { await sleep(t===0?0:t===400?200:100); await shot(`42-back-${t}ms`); }
await sleep(800); await shot("43-back-arrived");
log("back: pop open?", await b.eval(`!document.getElementById('cite-pop').hidden`));
// phone
await b.viewport(390, 844, true);
await b.go(B + "/?mock=1", 1500); await shot("50-phone-landing");
await b.go(PLAIN, 2500); await shot("51-phone-answer");
log("phone hover media fine?", await b.eval(`matchMedia('(hover: hover) and (pointer: fine)').matches`));
r = await b.rect('.cite[data-n="2"]'); 
await b.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[{x:r.x,y:r.y}]}); await b.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]}); await sleep(400);
await shot("52-phone-card");
log("phone pop", await b.eval(`JSON.stringify({mode:document.getElementById('cite-pop').dataset.mode, r:document.getElementById('cite-pop').getBoundingClientRect(), sw:document.documentElement.scrollWidth})`));
await b.go(TVN, 2500); await full("53-phone-tvn-full");
await b.go(B + "/graph/1256?mock=1&q=x", 4000); await shot("54-phone-graph");
await b.go(B + "/article/1256", 2500); await shot("55-phone-history");
log("phone history overflow", await b.eval(`document.documentElement.scrollWidth`));
// reduced motion card
await b.viewport(1440, 900); await b.reduced(true); await b.go(PLAIN, 2000);
r = await b.rect('.cite[data-n="1"]'); await b.click(r.x, r.y); await sleep(30); await shot("60-reduced-card-30ms");
// break: long question
await b.reduced(false);
await b.go(B + "/?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi ja miksi Neuvostoliitto hyökkäsi Suomeen ilman sodanjulistusta vaikka maiden välillä oli voimassa hyökkäämättömyyssopimus".repeat(2)), 2500); await shot("61-long-question");
// live (no mock) ask stub
await b.go(B + "/?q=" + encodeURIComponent("Kuka oli Mannerheim?"), 6000); await shot("62-live-stub");
log("live status", await b.eval(`document.getElementById('status').innerText + ' || ' + document.getElementById('answer').innerText.slice(0,200)`));
log("errors", JSON.stringify(b.log.errors));
console.log(out.join("\n"));
await b.close();
