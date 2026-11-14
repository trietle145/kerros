import { launch, sleep } from "../eval/cdp.mjs";
import { writeFileSync } from "node:fs";
const D = "C:/Users/hvhun/junction_hackathon/.claude/frontend-team/ux/shots";
const b = await launch(9351), B = "http://127.0.0.1:5006";
const shot = async n => { const r = await b.send("Page.captureScreenshot", { format: "png" }); writeFileSync(`${D}/${n}.png`, Buffer.from(r.data, "base64")); };
const full = async n => { const r = await b.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true }); writeFileSync(`${D}/${n}.png`, Buffer.from(r.data, "base64")); };
const out = []; const log = (...a) => out.push(a.join(" "));
const PLAIN = B + "/?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi?");
const TVN = B + "/?mock=1&q=" + encodeURIComponent("Mitä Wikipedia sanoi punavangeista vuonna 2007, ja mitä on muuttunut?");
await b.viewport(1440, 900);
// landing
await b.go(B + "/?mock=1", 1500); await shot("01-landing-1440");
// loading frames via typing
await b.eval(`document.getElementById('q').value='Milloin talvisota alkoi?'`);
await b.eval(`document.getElementById('ask-form').requestSubmit()`);
await b.frames.call(b, "x", []);
for (const t of [0,100,200,400]) { await sleep(t===0?0:(t===100?100:t===200?100:200)); await shot(`02-submit-${t}ms`); }
await sleep(1500); await full("03-answer-full-1440");
log("answer text:", await b.eval(`document.getElementById('answer').innerText.slice(0,600)`));
log("status:", await b.eval(`document.getElementById('status').innerText`));
log("cite count", await b.eval(`document.querySelectorAll('.cite').length`), "cite size", JSON.stringify(await b.rect('.cite')));
// hover peek timing frames
let r = await b.rect('.cite[data-n="1"]');
await b.mouse("mouseMoved", r.x, r.y);
for (const t of [0,150,300,450]) { await sleep(t?150:0); await shot(`04-peek-${t}ms`); }
log("peek rect", await b.eval(`JSON.stringify(document.getElementById('cite-pop').getBoundingClientRect())`));
// move to next marker
r = await b.rect('.cite[data-n="2"]'); await b.mouse("mouseMoved", r.x, r.y); await sleep(60); await shot("05-peek-move-60ms");
// click card frames
await b.mouse("mousePressed", r.x, r.y); await b.mouse("mouseReleased", r.x, r.y);
for (const t of [0,100,200]) { await sleep(t?100:0); await shot(`06-card-${t}ms`); }
log("card links", await b.eval(`[...document.querySelectorAll('#cite-pop a')].map(a=>a.textContent.trim()+' '+a.href).join(' | ')`));
log("card covers text? pop", await b.eval(`JSON.stringify(document.getElementById('cite-pop').getBoundingClientRect())`));
// show more
const more = await b.eval(`!document.querySelector('#cite-pop .more')?.hidden`); log("show more visible", more);
// last cite near bottom: scroll so a cite sits near the viewport bottom
await b.click(1300, 120); await sleep(200);
const ns = await b.eval(`[...document.querySelectorAll('.cite')].map(c=>c.dataset.n).join(',')`); log("cite order", ns);
await b.eval(`(()=>{const c=[...document.querySelectorAll('.cite')].pop(); scrollBy(0, c.getBoundingClientRect().top - innerHeight + 60)})()`); await sleep(200);
r = await b.eval(`(()=>{const c=[...document.querySelectorAll('.cite')].pop().getBoundingClientRect(); return {x:c.x+c.width/2,y:c.y+c.height/2}})()`);
await b.click(r.x, r.y); await sleep(300); await shot("07-card-near-bottom");
log("near bottom side", await b.eval(`document.getElementById('cite-pop').dataset.side`), JSON.stringify(await b.eval(`JSON.stringify(document.getElementById('cite-pop').getBoundingClientRect())`)));
// keyboard flow
await b.key("Escape","Escape",27); await sleep(200);
await b.eval(`scrollTo(0,0); document.getElementById('q').focus()`);
const seq = [];
for (let i = 0; i < 8; i++) { await b.key("Tab","Tab",9); await sleep(80); seq.push(await b.eval(`(()=>{const a=document.activeElement; return a.tagName+'.'+a.className+(a.dataset.n?'#'+a.dataset.n:'')+' pop:'+(document.getElementById('cite-pop').hidden?'-':document.getElementById('cite-pop').dataset.mode)})()`)); }
log("tab seq", seq.join(" > "));
await shot("08-kbd-focus-peek");
await b.key("Enter","Enter",13,"\r"); await sleep(300);
const seq2 = [];
for (let i = 0; i < 5; i++) { await b.key("Tab","Tab",9); await sleep(80); seq2.push(await b.eval(`(()=>{const a=document.activeElement; return a.tagName+'.'+a.className+' '+(a.textContent||'').trim().slice(0,20)+' pop:'+(document.getElementById('cite-pop').hidden?'-':document.getElementById('cite-pop').dataset.mode)})()`)); }
log("after enter tab seq", seq2.join(" > "));
await shot("09-kbd-card-tabbed");
await b.key("Escape","Escape",27); await sleep(200);
log("after esc focus", await b.eval(`document.activeElement.className+' '+document.activeElement.dataset.n`));
// related section
await b.eval(`document.getElementById('related').scrollIntoView()`); await sleep(300); await shot("10-related");
// tvn
await b.go(TVN, 2500); await full("11-tvn-full");
r = await b.rect('.cite[data-n="1"]'); await b.mouse("mouseMoved", r.x, r.y); await sleep(500); await shot("12-tvn-peek");
await b.click(r.x, r.y); await sleep(300); await shot("13-tvn-card");
log("tvn status", await b.eval(`document.getElementById('status').innerText`));
log("tvn eras", await b.eval(`JSON.stringify(JSON.parse(sessionStorage.lastAsk).res.sources.map(s=>[s.n,s.era,s.title]))`));
// error: live ask without mock, with bogus param? use empty
await b.go(B + "/", 1200); await b.eval(`document.getElementById('ask-form').requestSubmit()`); await sleep(400); await shot("14-empty-error");
log("errors", JSON.stringify(b.log.errors));
console.log(out.join("\n"));
await b.close();
