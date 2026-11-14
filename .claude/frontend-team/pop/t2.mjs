import { launch, sleep } from "../eval/cdp.mjs";
const b = await launch(9342), B = "http://127.0.0.1:5006", out = [];
const st = () => b.eval(`JSON.stringify({hidden: document.getElementById('cite-pop').hidden, mode: document.getElementById('cite-pop').dataset.mode, side: document.getElementById('cite-pop').dataset.side, sheet: !!document.getElementById('cite-pop').dataset.sheet, title: document.querySelector('#cite-pop h3')?.textContent, marks: document.querySelectorAll('#cite-pop mark').length})`);
await b.viewport(1440, 900);
await b.go(B + "/?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi?"), 3000);
out.push("chips " + await b.eval(`document.querySelectorAll('.src-chip').length`) + " health dots " + await b.eval(`[...document.querySelectorAll('.src-chip')].map(c=>c.dataset.health||'-').join(',')`));
out.push("status: " + await b.eval(`document.getElementById('status').innerText.replace(/\\s+/g,' ')`));
let r = await b.rect('.cite[data-n="2"]');
await b.mouse("mouseMoved", r.x, r.y); await sleep(500);
out.push("peek: " + await st()); await b.shot("q1-peek");
// move to marker 3 (should not be covered now)
let r3 = await b.rect('.cite[data-n="3"]');
await b.mouse("mouseMoved", r3.x, r3.y); await sleep(200);
out.push("peek3: " + await st());
// click the preview itself -> card
const pr = await b.rect('#cite-pop');
await b.click(pr.x, pr.y); await sleep(350);
out.push("after clicking preview: " + await st()); await b.shot("q2-card");
await b.clickSel('.pop-close'); await sleep(300);
out.push("close button: " + await st());
// chip opens card
await b.clickSel('.src-chip[data-n="1"]'); await sleep(350);
out.push("chip card: " + await st()); await b.shot("q3-chip-card");
await b.key("Escape", "Escape", 27); await sleep(250);
// rewind
out.push("rewind visible: " + await b.eval(`!document.getElementById('rewind').hidden`));
await b.eval(`(()=>{const r=document.getElementById('rw-range'); r.dispatchEvent(new Event('pointerdown',{bubbles:true})); r.value=2008; r.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await sleep(6000);
out.push("rewind 2008: " + await b.eval(`document.getElementById('rw-sum').textContent`) + " | markers " + await b.eval(`[...document.querySelectorAll('.cite')].map(c=>c.dataset.n+':'+(c.dataset.rw||'')).join(' ')`) + " | gone " + await b.eval(`document.querySelectorAll('.sent.rw-gone').length`));
await b.shot("q4-rewind");
await b.clickSel('.cite[data-n="1"]'); await sleep(400);
out.push("card in 2008: " + await b.eval(`document.querySelector('#cite-pop .rw-note')?.textContent`));
await b.shot("q5-rewind-card");
await b.key("Escape", "Escape", 27); await sleep(200);
// keyboard: tab to a marker -> peek without animation, Enter -> card, Tab out -> closes
await b.eval(`document.querySelector('.cite[data-n="1"]').focus({focusVisible:true})`); await sleep(100);
await b.key("Enter", "Enter", 13, "\r"); await sleep(200);
out.push("kbd card: " + await st() + " focus " + await b.eval(`document.activeElement.id`));
for (let i = 0; i < 8; i++) { await b.key("Tab", "Tab", 9); await sleep(60); }
out.push("after tabbing out: " + await st() + " focus " + await b.eval(`document.activeElement.className`));
// then vs now
await b.go(B + "/?mock=1&q=" + encodeURIComponent("Mitä Wikipedia sanoi punavangeista vuonna 2007, ja mitä on muuttunut?"), 3000);
out.push("tvn: date=" + await b.eval(`document.getElementById('as-of').value`) + " then-markers " + await b.eval(`document.querySelectorAll('.cite[data-era=then]').length`) + " rewind hidden " + await b.eval(`document.getElementById('rewind').hidden`));
await b.shot("q6-tvn");
// phone sheet
await b.viewport(390, 844, true);
await b.go(B + "/?mock=1&q=" + encodeURIComponent("Milloin talvisota alkoi?"), 3000);
await b.clickSel('.cite[data-n="2"]'); await sleep(500);
out.push("phone: " + await st() + " scrim " + await b.eval(`!document.getElementById('cite-scrim').hidden`) + " overflow " + await b.eval(`document.documentElement.scrollWidth > innerWidth`));
await b.shot("q7-phone-sheet");
await b.click(195, 100); await sleep(400);
out.push("phone tap scrim closes: " + await b.eval(`document.getElementById('cite-pop').hidden`));
await b.viewport(1440, 900);
await b.go(B + "/?mock=1", 1500); await b.shot("q8-landing");
out.push("errors: " + JSON.stringify(b.log.errors));
out.push("failed requests: " + JSON.stringify(b.log.requests.filter(x => !/^2|^3/.test(x))));
console.log(out.join("\n"));
await b.close();
