import { launch, sleep } from "../eval/cdp.mjs";
const b = await launch(9343), B = "http://127.0.0.1:5006", out = [];
const ev = x => b.eval(x);
await b.viewport(1440, 900);

// phone sheet (fixed)
await b.viewport(390, 844, true);
await b.go(B + "/?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi?"), 3000);
await b.clickSel('.cite[data-n="2"]'); await sleep(500);
out.push("phone sheet: " + await ev(`JSON.stringify({sheet: document.getElementById('cite-pop').hasAttribute('data-sheet'), rect: document.getElementById('cite-pop').getBoundingClientRect().top|0, scrim: !document.getElementById('cite-scrim').hidden})`));
await b.shot("r1-phone-sheet");
await b.click(195, 120); await sleep(450);
out.push("scrim tap closes: " + await ev(`document.getElementById('cite-pop').hidden`));

// drift
await b.viewport(1440, 900);
await b.go(B + "/drift", 2500);
out.push("drift: lines " + await ev(`document.querySelectorAll('#d-svg .line').length`) + " flips " + await ev(`document.querySelectorAll('.flip').length`) + " dirs " + await ev(`document.querySelectorAll('.dir-bars li').length`));
let r = await b.rect('#d-svg');
await b.mouse("mouseMoved", r.l + r.w * 0.55, r.t + r.h / 2); await sleep(200);
out.push("tooltip: " + await ev(`document.getElementById('d-tip').innerText.replace(/\\s+/g,' ').slice(0,120)`));
await b.shot("r2-drift");
await b.clickSel('[data-mode="count"]'); await sleep(300); await b.shot("r3-drift-count");
await b.clickSel('[data-id="camps"]'); await sleep(1200);
out.push("camps: " + await ev(`document.getElementById('d-title').textContent + ' / flips ' + document.querySelectorAll('.flip').length`));
await b.viewport(390, 844, true); await b.go(B + "/drift", 2500);
out.push("drift phone overflow: " + await ev(`document.documentElement.scrollWidth > innerWidth`));
await b.shot("r4-drift-phone");
await b.viewport(1440, 900);

// tools: citation finder
await b.go(B + "/tools", 1500);
await b.clickSel('[data-example]'); await sleep(6000);
out.push("cite: " + await ev(`document.querySelectorAll('#cite-out .card').length + ' cards, refs ' + document.querySelectorAll('#cite-out .refs li').length`));
await b.shot("r5-cite");
// contradictions
await b.clickSel('#tab-contra'); await sleep(200);
await b.clickSel('#contra-quick [data-page="1150"]'); await sleep(8000);
out.push("contra: " + await ev(`document.querySelectorAll('#contra-out .pair').length + ' pairs; first: ' + (document.querySelector('#contra-out .pair-facts')?.innerText||'')`));
await b.shot("r6-contra");
// radar
await b.clickSel('#tab-radar'); await sleep(5000);
out.push("radar rows: " + await ev(`document.querySelectorAll('.radar-table tbody tr').length`));
await b.clickSel('.radar-table tbody tr'); await sleep(4000);
out.push("radar detail: " + await ev(`document.querySelectorAll('.contested li').length + ' paragraphs; ' + (document.querySelector('.radar-detail h2')?.textContent||'')`));
await b.shot("r7-radar");
out.push("no editor names in radar: " + await ev(`!/käyttäjä|user:/i.test(document.getElementById('radar-out').innerText)`));

// lesson
await b.go(B + "/lesson/8295?q=Mainila", 9000);
out.push("lesson: " + await ev(`document.getElementById('l-title').textContent + ', steps shown ' + document.querySelectorAll('.step-card').length`));
await b.clickSel('#l-more'); await sleep(400);
await b.clickSel('#l-all'); await sleep(500);
await b.clickSel('#l-start'); await sleep(500);
out.push("quiz questions: " + await ev(`document.querySelectorAll('.question').length`));
for (let i = 0; i < 4; i++) { try { await b.clickSel(`#q-${i} .option`); await sleep(150); } catch {} }
out.push("score: " + await ev(`document.getElementById('l-score').innerText`));
await b.full("r8-lesson");

// history: explain
await b.go(B + "/article/8295?as_of=2015-06-01", 3000);
await b.clickSel('#explain'); await sleep(5000);
out.push("explain: " + await ev(`document.getElementById('explain-out').innerText.replace(/\\s+/g,' ').slice(0,220)`));
await b.shot("r9-explain");

// error page and graph
await b.go(B + "/no-such-page", 1000);
out.push("404 page: " + await ev(`document.querySelector('.page-error h1')?.textContent`));
await b.go(B + "/graph/8295?mock=1", 4000);
await b.shot("r10-graph");
out.push("graph nodes in list: " + await ev(`document.querySelectorAll('#graph-nodelist button').length`));

out.push("errors: " + JSON.stringify(b.log.errors));
out.push("bad requests: " + JSON.stringify(b.log.requests.filter(x => !/^(2|3)\d\d /.test(x) && !/no-such-page/.test(x))));
console.log(out.join("\n"));
await b.close();
