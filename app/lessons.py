"""Guided lessons (new file, B with A's agreement; read-only): the graph's reading path becomes a
short lesson. Each step is an article's opening paragraph (cited to its exact version); a quiz at
the end asks about what the steps said. Quiz questions come from the LLM when a key is set and pass
validation, else from the text itself: a sentence with a year, the year blanked out.

    GET /api/lesson/<page_id>?q=...   {"title", "steps": [...], "quiz": [...], "source"}

    python -m app.lessons             # self-check on Mainilan laukaukset (read-only)
"""
import json
import random
import re
from contextlib import closing
from functools import lru_cache

from flask import Blueprint, request

from app.db import connect

bp = Blueprint("lessons", __name__)
YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")


def sentences(text):
    return [s.strip() for s in re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÅÄÖ0-9])", text or "") if len(s.strip()) > 30]


def cloze_quiz(steps, n=4, seed=0):
    """Year questions from the steps' own sentences: the year blanked, three nearby years from the
    same lesson (or close by) as the wrong options. One question per step first."""
    rnd = random.Random(seed)
    pool = sorted({int(y) for s in steps for y in YEAR.findall(s["text"])})
    picks, used = [], set()
    for rnd_pass in (0, 1):
        for i, s in enumerate(steps):
            for sent in sentences(s["text"]):
                years = YEAR.findall(sent)
                if not years or sent in used or (rnd_pass == 0 and any(p["step"] == i for p in picks)):
                    continue
                year = int(years[0])
                near = sorted((y for y in pool if y != year), key=lambda y: abs(y - year))[:3]
                for d in (1, -1, 2, -2, 5, -5, 10):        # top up when the lesson has few years
                    if len(near) < 3 and year + d not in near and year + d <= 2026:
                        near.append(year + d)
                options = [year] + near[:3]
                rnd.shuffle(options)
                picks.append({"q": sent.replace(years[0], "____", 1), "options": [str(o) for o in options],
                              "answer": options.index(year), "step": i, "explain": sent})
                used.add(sent)
                break
            if len(picks) == n:
                return picks
    return picks


def llm_quiz(steps, question):
    """Up to 4 multiple-choice questions written by the model from the steps only; None if no key,
    the call fails, or the reply does not validate (then the cloze quiz is used)."""
    from scripts.common import env
    if not env().get("LLM_API_KEY"):
        return None
    try:
        from app.llm import complete
        texts = "\n\n".join(f"[{i}] {s['title']}\n{s['text']}" for i, s in enumerate(steps))
        reply = complete("You write a short quiz for a reader who just read these Finnish Wikipedia passages. "
                         "Write 4 multiple-choice questions in English, each answerable from one passage only, "
                         "4 options each, exactly one correct. Reply with JSON only: "
                         '[{"q": "...", "options": ["...", "...", "...", "..."], "answer": 0, "step": 0, "explain": "..."}] '
                         "where step is the passage number and explain quotes the passage sentence that holds the answer.",
                         f"Passages:\n\n{texts}" + (f"\n\nThe reader's question was: {question}" if question else ""),
                         max_tokens=1500)
        quiz = json.loads(reply[reply.index("["): reply.rindex("]") + 1])
        ok = [q for q in quiz if isinstance(q.get("options"), list) and len(q["options"]) == 4
              and isinstance(q.get("answer"), int) and 0 <= q["answer"] < 4
              and isinstance(q.get("step"), int) and 0 <= q["step"] < len(steps) and q.get("q")]
        return ok[:4] if len(ok) >= 2 else None
    except Exception:
        return None


@lru_cache(maxsize=64)
def lesson(page_id, question=""):
    from app.graph import graph, reading_path
    g, p = graph(page_id), reading_path(page_id)
    if not g or not p:
        return None
    nodes = {n["id"]: n for n in g["nodes"]}
    ids = [s["id"] for s in p["path"]]
    marks = ",".join("?" * len(ids))
    with closing(connect()) as con:
        cur = con.cursor()
        cur.execute(f"SELECT page_id, position, heading, text FROM passage WHERE page_id IN ({marks}) AND position < 2 "
                    "ORDER BY page_id, position", ids)
        texts = {}
        for pid, pos, heading, text in cur.fetchall():
            texts.setdefault(pid, []).append(text)
    steps = []
    for s in p["path"]:
        n = nodes[s["id"]]
        text = "\n".join(texts.get(s["id"], [n["lead"]]))
        lead = " ".join(sentences(text)[:3]) or n["lead"]
        steps.append({"id": n["id"], "title": n["title"], "why": s["why"], "relation": n["relation"],
                      "lead": lead, "text": text[:2500], "rev_id": n["rev_id"],
                      "url": f"https://fi.wikipedia.org/?oldid={n['rev_id']}"})
    quiz, source = llm_quiz(steps, question), "llm"
    if not quiz:
        quiz, source = cloze_quiz(steps, seed=page_id), "heuristic"
    for q in quiz:
        q["url"] = steps[q["step"]]["url"]
        q["title"] = steps[q["step"]]["title"]
    return {"page_id": g["main"], "title": nodes[g["main"]]["title"], "question": question,
            "steps": [{k: v for k, v in s.items() if k != "text"} for s in steps], "quiz": quiz, "source": source}


@bp.get("/api/lesson/<int:page_id>")
def api_lesson(page_id):
    out = lesson(page_id, (request.args.get("q") or "").strip()[:300])
    return out if out else ({"error": f"no article {page_id}"}, 404)


if __name__ == "__main__":
    steps = [{"title": "A", "text": "Talvisota alkoi vuonna 1939 Neuvostoliiton hyökkäyksellä Suomeen."},
             {"title": "B", "text": "Moskovan rauha solmittiin vuonna 1940 ja sota päättyi siihen."}]
    q = cloze_quiz(steps)
    assert len(q) == 2 and all(x["options"][x["answer"]] in x["explain"] and "____" in x["q"] for x in q), q
    assert all(len(set(x["options"])) == 4 for x in q)
    print("quiz rules ok")
    les = lesson(8295)
    assert les["steps"][-1]["id"] == les["page_id"] and les["quiz"]
    print(les["title"], [s["title"] for s in les["steps"]], les["source"], len(les["quiz"]), "questions")
    for x in les["quiz"]:
        print(" ", x["q"][:90], x["options"], "->", x["options"][x["answer"]])
    print("ok")
