// Minimal CDP driver for headless Edge (Node 22+ global WebSocket). Evaluator only.
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
export const OUT = "C:/Users/hvhun/junction_hackathon/.claude/frontend-team/eval/shots";
mkdirSync(OUT, { recursive: true });
export const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function launch(port = 9333) {
  const proc = spawn(EDGE, [`--remote-debugging-port=${port}`, "--headless=new", "--no-first-run", "--disable-gpu-sandbox",
    `--user-data-dir=C:/Users/hvhun/AppData/Local/Temp/evaledge${port}`, "--window-size=1440,900", "about:blank"], { stdio: "ignore" });
  let ver;
  for (let i = 0; i < 50; i++) { try { ver = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if (ver.length) break; } catch {} await sleep(200); }
  const page = ver.find(t => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener("open", r));
  let id = 0; const pending = new Map(); const listeners = [];
  ws.addEventListener("message", e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
    else if (m.method) listeners.forEach(f => f(m));
  });
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
  const log = { console: [], errors: [], requests: [], failed: [] };
  listeners.push(m => {
    if (m.method === "Runtime.consoleAPICalled") log.console.push(m.params.type + ": " + m.params.args.map(a => a.value ?? a.description ?? "").join(" "));
    if (m.method === "Runtime.exceptionThrown") log.errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === "Network.responseReceived") log.requests.push(m.params.response.status + " " + m.params.response.url);
    if (m.method === "Network.loadingFailed") log.failed.push(m.params.errorText + " " + m.params.requestId);
    if (m.method === "Log.entryAdded") log.console.push("log." + m.params.entry.level + ": " + m.params.entry.text + " " + (m.params.entry.url || ""));
  });
  await send("Runtime.enable"); await send("Network.enable"); await send("Page.enable"); await send("Log.enable");
  const api = {
    send, log, proc, listeners,
    async viewport(w, h, mobile = false) { await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile }); },
    async reduced(on) { await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: on ? "reduce" : "no-preference" }] }); },
    async go(url, wait = 1500) {
      const loaded = new Promise(r => { const f = m => { if (m.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(f), 1); r(); } }; listeners.push(f); });
      await send("Page.navigate", { url }); await Promise.race([loaded, sleep(10000)]); await sleep(wait);
    },
    async eval(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) return "EVAL ERROR: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    },
    async shot(name) { const r = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); return name; },
    async full(name) { const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); },
    async mouse(type, x, y) { await send("Input.dispatchMouseEvent", { type, x, y, button: type === "mouseMoved" ? "none" : "left", clickCount: 1 }); },
    async click(x, y) { await api.mouse("mouseMoved", x, y); await api.mouse("mousePressed", x, y); await api.mouse("mouseReleased", x, y); },
    async key(key, code = key, vk = 0, text) { await send("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: vk, text }); await send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: vk }); },
    async type(text) { await send("Input.insertText", { text }); },
    async rect(sel) { return api.eval(`(()=>{const e=document.querySelector(${JSON.stringify(sel)}); if(!e) return null; const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height,l:r.left,t:r.top}})()`); },
    async clickSel(sel) { const r = await api.rect(sel); if (!r) throw new Error("no " + sel); await api.click(r.x, r.y); return r; },
    async frames(prefix, times) { let t0 = Date.now(); for (const t of times) { const d = t - (Date.now() - t0); if (d > 0) await sleep(d); await api.shot(`${prefix}-${t}ms`); } },
    async close() { try { await send("Browser.close"); } catch {} proc.kill(); },
  };
  return api;
}
