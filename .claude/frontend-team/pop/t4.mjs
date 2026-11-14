import { launch, sleep } from "../eval/cdp.mjs";
const b = await launch(9344), B = "http://127.0.0.1:5001", out = [];
const ev = x => b.eval(x);
await b.viewport(1440, 900);
await b.go(B + "/?mock=1", 1500);
out.push("hero: " + await ev(`document.querySelector('.hero h1').textContent`));
await b.shot("t4-landing");

// citation finder
await b.go(B + "/tools", 1500);
await b.clickSel('[data-example]'); await sleep(7000);
out.push("cite: sats " + await ev(`document.querySelectorAll('.sat').length`) + " detail refs " + await ev(`document.querySelectorAll('#cite-detail .ref-chip').length`) + " | svg h " + await ev(`document.querySelector('.const svg').getBoundingClientRect().height|0`));
await b.shot("t4-cite");
const s2 = await b.rect('.sat[data-i="1"]');
await b.mouse("mouseMoved", s2.x, s2.y); await sleep(300);
out.push("tip: " + await ev(`document.getElementById('viz-tip').classList.contains('on') + ' | ' + document.getElementById('viz-tip').innerText.replace(/\s+/g,' ').slice(0,100)`));
await b.click(s2.x, s2.y); await sleep(400);
out.push("selected: " + await ev(`document.querySelector('.sat.is-sel').dataset.i + ' | ' + document.querySelector('#cite-detail h3').textContent`));
await b.shot("t4-cite-sel");

// contradictions
await b.clickSel('#tab-contra'); await sleep(200);
await b.clickSel('#contra-quick [data-page="1150"]'); await sleep(7000);
out.push("contra rows: " + await ev(`document.querySelectorAll('.db-row').length + ' | ' + document.querySelector('.viz-sum')?.innerText`));
await b.shot("t4-contra");
await b.clickSel('.db-main'); await sleep(500);
out.push("open: " + await ev(`document.querySelector('.db-row.is-open .snip')?.innerText.slice(0,100)`));
await b.shot("t4-contra-open");

// radar
await b.clickSel('#tab-radar'); await sleep(4500);
out.push("heat rows: " + await ev(`document.querySelectorAll('.heat-row').length + ' cells ' + document.querySelectorAll('.heat-cell').length`));
await b.shot("t4-radar");
const hc = await b.rect('.heat-row:nth-child(3) .heat-cell:nth-child(12)');
await b.mouse("mouseMoved", hc.x, hc.y); await sleep(300);
out.push("heat tip: " + await ev(`document.getElementById('viz-tip').innerText.replace(/\s+/g,' ')`));
await b.clickSel('.heat-row:nth-child(4) .heat-name'); await sleep(5000);
out.push("lanes: " + await ev(`document.querySelectorAll('.lane').length + ' ticks ' + document.querySelectorAll('.tick').length`));
await b.shot("t4-radar-detail");

// phone
await b.viewport(390, 844, true);
await b.go(B + "/tools?tool=radar", 4500);
out.push("phone radar overflow: " + await ev(`document.documentElement.scrollWidth > innerWidth`));
await b.shot("t4-phone-radar");
await b.go(B + "/tools?tool=contra&page=1150", 7000);
out.push("phone contra overflow: " + await ev(`document.documentElement.scrollWidth > innerWidth`));
await b.shot("t4-phone-contra");
await b.go(B + "/tools?tool=cite&text=" + encodeURIComponent("Talvisota alkoi 30. marraskuuta 1939 ilman sodanjulistusta."), 7000);
out.push("phone cite overflow: " + await ev(`document.documentElement.scrollWidth > innerWidth`));
await b.shot("t4-phone-cite");
out.push("errors: " + JSON.stringify(b.log.errors));
console.log(out.join("\n"));
await b.close();
