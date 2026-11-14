// "Explain this edit" on the history page (owner: ui): the facts of one edit from insights.py, plus a
// plain-English summary when the server has an LLM key. Never shows who made the edit.
import { explain } from "/static/api.js";

const btn = document.getElementById("explain"), out = document.getElementById("explain-out");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
const num = n => Number(n).toLocaleString("en-US");
const signed = n => (n > 0 ? "+" : n < 0 ? "−" : "±") + num(Math.abs(n));

btn?.addEventListener("click", async () => {
  const open = btn.getAttribute("aria-expanded") === "true";
  btn.setAttribute("aria-expanded", !open);
  out.hidden = open;
  if (open || out.dataset.done) return;
  out.innerHTML = `<p class="tool-loading"><i></i>Comparing this version with the one before…</p>`;
  try {
    const e = await explain(btn.dataset.page, btn.dataset.rev), f = e.facts;
    const facts = [
      f.is_revert && `<span class="pill pill-warn">a revert: it brought back an earlier version</span>`,
      `<span class="pill num">${signed(f.words_added - f.words_removed)} words (${num(f.words_added)} in, ${num(f.words_removed)} out)</span>`,
      f.refs && `<span class="pill num">${signed(f.refs)} reference${Math.abs(f.refs) === 1 ? "" : "s"}</span>`,
      f.links && `<span class="pill num">${signed(f.links)} link${Math.abs(f.links) === 1 ? "" : "s"}</span>`,
      f.numbers_out.length && `<span class="pill num">numbers out: ${f.numbers_out.map(esc).join(", ")}</span>`,
      f.numbers_in.length && `<span class="pill num">numbers in: ${f.numbers_in.map(esc).join(", ")}</span>`,
    ].filter(Boolean).join("");
    const nothing = !f.words_added && !f.words_removed;
    out.innerHTML = `<h2 class="kicker">What this edit changed</h2>
      ${e.summary ? `<p class="explain-summary">${esc(e.summary)}</p>` : ""}
      <p class="explain-facts">${facts}</p>
      ${f.sections.length ? `<p class="muted-note">In: ${f.sections.map(s => `<span lang="fi">${esc(s)}</span>`).join(", ")}</p>` : ""}
      ${nothing ? `<p class="muted-note">No change to the readable text: formatting, templates or references only (${signed(f.bytes)} bytes).</p>` :
        `<ol class="explain-changes">${e.changes.map(c => `<li><p class="kicker" lang="fi">${esc(c.section)}</p><p class="diff-body" lang="fi">
          ${c.context ? `…${esc(c.context)} ` : ""}${c.before ? `<del>${esc(c.before)}</del> ` : ""}${c.after ? `<ins>${esc(c.after)}</ins>` : ""}</p></li>`).join("")}</ol>`}
      <p class="muted-note"><a href="${esc(e.diff)}" target="_blank" rel="noopener">The full diff on Wikipedia ↗</a>
        ${e.source === "llm" ? " · Summary written by a language model from the facts above." : ""}</p>`;
    out.dataset.done = "1";
  } catch (err) {
    out.innerHTML = `<p class="alert"><span><b>That did not work.</b> ${esc(err.message)}</span></p>`;
  }
});
