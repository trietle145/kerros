import { launch, sleep } from "../eval/cdp.mjs";
const b = await launch(9346), B = "http://127.0.0.1:5001";
await b.viewport(390, 844, true);
await b.go(B + "/tools?tool=radar", 6000);
console.log(await b.eval(`(()=>{const c=document.querySelector('.heat-cell'); const g=document.querySelector('.heat-grid'); const r=c.getBoundingClientRect(); const cs=getComputedStyle(c); return JSON.stringify({w:r.width,h:r.height,x:r.x,op:cs.opacity,bg:cs.backgroundColor,anim:cs.animationName, gridCols:getComputedStyle(g).gridTemplateColumns.slice(0,80), heatW:document.querySelector('.heat').clientWidth, gridW:g.getBoundingClientRect().width})})()`));
await b.shot("t6-phone-radar");
await b.close();
