// Lesson page (owner: ui): the graph's reading path as steps you reveal one at a time, then a quiz
// whose answers link back to the passage they come from. Data from lessons.py.
import { lesson } from "/static/api.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const { pageId, q } = document.body.dataset;
const mock = new URLSearchParams(location.search).get("mock");
let L, shown = 1, answered = 0, score = 0;

lesson(pageId, q).then(r => {
  L = r;
  $("l-title").textContent = r.title;
  document.title = `Lesson: ${r.title} · Kerros`;
  $("lesson").removeAttribute("aria-busy");
  render();
}).catch(e => {
  $("lesson").removeAttribute("aria-busy");
  $("l-steps").innerHTML = `<li><p class="alert"><span><b>The lesson could not be built.</b> ${esc(e.message)}</span></p></li>`;
});

const graphUrl = id => `/graph/${id}?q=${encodeURIComponent(q || "")}${mock ? "&mock=" + mock : ""}`;

function step(s, i) {
  const last = i === L.steps.length - 1;
  return `<li class="step-card${last ? " is-main" : ""}" id="step-${i}" style="--i:${i}" tabindex="-1">
    <span class="step-n" aria-hidden="true">${i + 1}</span>
    <div class="step-body">
      <h2 lang="fi">${esc(s.title)}</h2>
      <p class="step-why">${esc(s.why)}</p>
      <p class="step-text" lang="fi">${esc(s.lead)}</p>
      <p class="step-actions"><a class="btn btn-quiet" href="${esc(s.url)}" target="_blank" rel="noopener">Read on Wikipedia ↗</a>
        <a class="btn btn-quiet" href="/article/${s.id}">History</a><a class="btn btn-quiet" href="${graphUrl(s.id)}">Graph</a></p>
    </div></li>`;
}

function render() {
  $("l-steps").innerHTML = L.steps.slice(0, shown).map(step).join("");
  $("l-progress").innerHTML = L.steps.map((_, i) => `<i class="${i < shown ? "on" : ""}"></i>`).join("");
  const next = $("l-next");
  next.hidden = false;
  next.innerHTML = shown < L.steps.length
    ? `<button class="btn btn-primary" type="button" id="l-more">Next: <span lang="fi">${esc(L.steps[shown].title)}</span></button>
       <button class="linkish" type="button" id="l-all">Show all steps</button>`
    : (L.quiz.length && $("l-quiz").hidden ? `<button class="btn btn-primary" type="button" id="l-start">Check what you learned · ${L.quiz.length} questions</button>` : "");
}

function reveal(all) {
  const from = shown;
  shown = all ? L.steps.length : shown + 1;
  render();
  const card = $(`step-${from}`);
  if (!reduced()) for (let i = from; i < shown; i++)
    $(`step-${i}`).animate([{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }],
                           { duration: 320, delay: (i - from) * 60, easing: "cubic-bezier(0.23, 1, 0.32, 1)", fill: "backwards" });
  card.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
  card.focus({ preventScroll: true });
}

function quiz() {
  const box = $("l-quiz");
  box.hidden = false;
  box.innerHTML = `<h2 class="kicker" id="quiz-head">Check what you learned</h2>
    <p class="muted-note">${L.source === "llm" ? "Questions written by the language model from the passages above." : "Questions made from the passages above: find the missing year."}</p>
    <ol class="quiz-list">${L.quiz.map((x, i) => `<li class="question" id="q-${i}" style="--i:${i}">
      <p class="q-text" lang="${L.source === "llm" ? "en" : "fi"}">${esc(x.q).replace("____", `<span class="blank">____</span>`)}</p>
      <div class="options" role="group" aria-label="Answers to question ${i + 1}">${x.options.map((o, k) =>
        `<button class="option" type="button" data-q="${i}" data-k="${k}">${esc(o)}</button>`).join("")}</div>
      <p class="q-why" hidden></p></li>`).join("")}</ol>
    <p class="quiz-score" id="l-score" aria-live="polite"></p>`;
  $("l-next").hidden = true;
  if (!reduced()) box.animate([{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: "cubic-bezier(0.23, 1, 0.32, 1)" });
  box.querySelector(".option").focus({ preventScroll: false });
}

function choose(b) {
  const i = +b.dataset.q, k = +b.dataset.k, x = L.quiz[i], li = $(`q-${i}`);
  if (li.dataset.done) return;
  li.dataset.done = k === x.answer ? "right" : "wrong";
  answered++; if (k === x.answer) score++;
  for (const o of li.querySelectorAll(".option")) {
    o.disabled = true;
    if (+o.dataset.k === x.answer) o.classList.add("is-right");
    else if (o === b) o.classList.add("is-wrong");
  }
  const why = li.querySelector(".q-why");
  why.hidden = false;
  why.innerHTML = `${k === x.answer ? "Right." : `The answer is ${esc(x.options[x.answer])}.`} From <a href="${esc(x.url)}" target="_blank" rel="noopener" lang="fi">${esc(x.title)} ↗</a>:
    <q lang="fi">${esc(x.explain)}</q>`;
  if (answered === L.quiz.length) {
    $("l-score").innerHTML = `<b class="num">${score} of ${L.quiz.length}</b> ${score === L.quiz.length ? "All right. " : ""}
      <a href="${graphUrl(L.page_id)}">See how these articles connect →</a>`;
  }
}

document.addEventListener("click", e => {
  if (e.target.closest("#l-more")) reveal(false);
  else if (e.target.closest("#l-all")) reveal(true);
  else if (e.target.closest("#l-start")) quiz();
  else if (e.target.closest(".option")) choose(e.target.closest(".option"));
});
