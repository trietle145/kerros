"""Are the answers right, and does every citation hold? Answer-level eval over /ask's own code path.

    python eval/answers.py          # 25 questions, ~50 model calls (~$2, ~5 min); needs bge-m3 (~5 GB free)

Questions: eval/answer-questions.tsv (kind, question, expect), written from the passages in the
database. Per kind:
  fact         the answer contains the expected fact: `expect` is regex groups joined by " && ",
               every group must match (case-insensitive), alternatives inside a group with |
  then_vs_now  routed to the then-vs-now path, plus the fact check when `expect` is set
  none         Wikipedia doesn't answer it: pass = no sentence carries a citation
Every cited sentence of every answer goes to a judge call: do its cited passages state it?
"""
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.answer import answer      # noqa: E402
from app.llm import complete       # noqa: E402

JUDGE = """For each numbered sentence, say whether the passages cited for it state what the sentence says.
Paraphrase and translation are fine: the passages are Finnish, the sentences may be English.
A sentence that adds a fact the passages don't state is "no". Reply with one line per sentence,
"<n> yes" or "<n> no", nothing else."""


def has_fact(text, expect):
    return all(re.search(group, text, re.I) for group in expect.split(" && "))


def judge(a):
    """-> (supported, judged) for the answer's cited sentences."""
    src = {s["n"]: s for s in a["sources"]}
    cited = [s for s in a["answer"] if s["cites"]]
    if not cited:
        return 0, 0
    blocks = []
    for i, s in enumerate(cited, 1):
        passages = "\n".join(f"  [{c}] {src[c]['title']}: {src[c]['text']}" for c in s["cites"])
        blocks.append(f"Sentence {i}: {s['text']}\nCited passages:\n{passages}")
    verdicts = dict(re.findall(r"^\s*(\d+)\s+(yes|no)", complete(JUDGE, "\n\n".join(blocks)).lower(), re.M))
    return sum(verdicts.get(str(i)) == "yes" for i in range(1, len(cited) + 1)), len(cited)


def main():
    rows = list(csv.DictReader(open(Path(__file__).parent / "answer-questions.tsv", encoding="utf-8"),
                               delimiter="\t"))
    fact = [0, 0]; refusal = [0, 0]; support = [0, 0]; routed = [0, 0]; times = []
    for r in rows:
        t = time.perf_counter()
        a = answer(r["question"])
        times.append(time.perf_counter() - t)
        text = " ".join(s["text"] for s in a["answer"])
        ok_sup, n_sup = judge(a)
        support[0] += ok_sup; support[1] += n_sup
        marks = []
        if r["kind"] == "none":
            ok = not any(s["cites"] for s in a["answer"])
            refusal[0] += ok; refusal[1] += 1
            marks.append("refused" if ok else "ANSWERED")
        else:
            if r["kind"] == "then_vs_now":
                ok = a["kind"] == "then_vs_now"
                routed[0] += ok; routed[1] += 1
                marks.append("routed" if ok else "NOT ROUTED")
            if r["expect"]:
                ok = has_fact(text, r["expect"])
                fact[0] += ok; fact[1] += 1
                marks.append("fact" if ok else "FACT MISSING")
        marks.append(f"cites {ok_sup}/{n_sup}")
        print(f"\n{r['question']}  ({times[-1]:.1f} s; {', '.join(marks)})\n  {text}", flush=True)
    pct = lambda p: f"{p[0]}/{p[1]} ({p[0] / p[1]:.0%})" if p[1] else "-"     # noqa: E731
    print(f"\ncorrect facts         {pct(fact)}\nsupported citations   {pct(support)}"
          f"\ncorrect refusals      {pct(refusal)}\nthen-vs-now routed    {pct(routed)}"
          f"\nanswer time           median {sorted(times)[len(times) // 2]:.1f} s, max {max(times):.1f} s")


if __name__ == "__main__":
    assert has_fact("It began on November 30, 1939 and ended 13 March 1940.",
                    "30(th)? (of )?November|November 30(th)? && 13(th)? (of )?March|March 13(th)?")
    assert not has_fact("It ended in 1940.", "1940 && March")
    main()
