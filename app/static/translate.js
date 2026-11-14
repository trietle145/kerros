// "Translate" for any Finnish block, on every page (loaded by base.html):
//   <p id="x" lang="fi">…</p> <button class="tr-btn" type="button" data-target="x">Translate</button>
// Swaps the block's text to English from /api/translate (Opus-MT on our own server) and back.
// Translated text is marked as machine translation (CSS: [data-fi]::after), never passed off as
// Wikipedia's words. Works for content rendered later too (one delegated click listener).
document.addEventListener("click", async e => {
  const btn = e.target.closest(".tr-btn"), el = btn && document.getElementById(btn.dataset.target);
  if (!el || btn.disabled) return;
  if (el.dataset.fi) {                                  // back to the Finnish original
    el.textContent = el.dataset.fi;
    delete el.dataset.fi;
    el.lang = "fi";
    btn.textContent = "Translate";
    return;
  }
  const fi = el.textContent;
  btn.disabled = true;
  btn.textContent = "Translating…";
  try {
    const r = await fetch("/api/translate", { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify({ text: fi, from: "fi", to: "en" }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.translation) throw new Error(d.error || `HTTP ${r.status}`);
    el.dataset.fi = fi;
    el.textContent = d.translation;
    el.lang = "en";
    btn.textContent = "Show Finnish";
  } catch (err) {
    console.warn("translate:", err);
    btn.textContent = "Translation failed, try again";
  } finally {
    btn.disabled = false;
  }
});
