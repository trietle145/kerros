"""Machine translation (owner: A, backend). Helsinki-NLP Opus-MT models run on our own server: no
API, no key, no cost per call, and the text never leaves the server.

    POST /api/translate  {"text": "...", "to": "en"}            ->  {"translation", "model"}
                         {"texts": [...], "to": "fi"}           ->  {"translations", "model"}
                         "from" is optional (fi / sv / en, guessed from the words if missing)
    python -m app.translate      # self-check: split + language guess, then real translations

Source cards send one Finnish passage; the answer's "Show in English / Finnish" button sends its
sentences as a list, so each sentence keeps its own citation numbers on the page.
"""
import re
import threading
from functools import lru_cache

from flask import Blueprint, request

bp = Blueprint("translate", __name__)
MODELS = {("fi", "en"): "Helsinki-NLP/opus-mt-fi-en", ("fi", "sv"): "Helsinki-NLP/opus-mt-fi-sv",
          ("en", "fi"): "Helsinki-NLP/opus-mt-en-fi", ("sv", "fi"): "Helsinki-NLP/opus-mt-sv-fi",
          ("sv", "en"): "Helsinki-NLP/opus-mt-sv-en"}
MAX_CHARS = 4000         # a passage is <= ~300 words; more would tie up the CPU
# A sentence ends at . ! ? after a letter or a 4-digit year, before a capital; never after a day
# number: split after the "30." of "30. marraskuuta" and the model sees fragments and invents dates.
SPLIT = re.compile(r"(?:(?<=[^\W\d][.!?])|(?<=\d{4}[.!?]))\s+(?=[A-ZÅÄÖ])")
COMMON = {"fi": {"ja", "oli", "että", "joka", "hän", "mutta", "kun", "myös", "ovat", "sekä", "vuonna"},
          "sv": {"och", "är", "var", "det", "att", "som", "av", "för", "med", "på", "till"},
          "en": {"the", "and", "was", "is", "of", "to", "that", "by", "with", "were", "which"}}
_lock = threading.Lock()  # ponytail: one translation at a time on the 4-core server; a queue if busy


def guess_lang(text):
    """fi / sv / en by counting very common words. ponytail: fine for sentences and passages,
    not for a single word."""
    words = re.findall(r"\w+", text.lower())
    return max(COMMON, key=lambda lang: sum(w in COMMON[lang] for w in words))


@lru_cache(maxsize=3)
def _model(pair):
    from transformers import MarianMTModel, MarianTokenizer
    return MarianTokenizer.from_pretrained(MODELS[pair]), MarianMTModel.from_pretrained(MODELS[pair])


def _run(sentences, pair):
    """One batch through the model. Beam search (4): greedy decoding was twice as fast but lost
    meaning ("lavastama", staged -> "Soviet-style"). ~3 s for a typical passage, ~10 s for the
    longest."""
    tok, model = _model(pair)
    with _lock:
        out = model.generate(**tok(sentences, return_tensors="pt", padding=True, truncation=True),
                             num_beams=4, max_new_tokens=400)
    return tok.batch_decode(out, skip_special_tokens=True)


@lru_cache(maxsize=2000)
def translate(text, to="en", src="fi"):
    """A passage, split into sentences, line breaks kept; cached."""
    lines = [SPLIT.split(line) for line in text.splitlines() if line.strip()]
    done = iter(_run([s for line in lines for s in line], (src, to)))
    return "\n".join(" ".join(next(done) for _ in line) for line in lines)


@bp.post("/api/translate")
def api():
    d = request.get_json(silent=True) or {}
    texts, to = d.get("texts"), d.get("to", "en")
    single = texts is None
    texts = [d.get("text") or ""] if single else texts
    if not isinstance(texts, list) or not all(isinstance(t, str) and t.strip() for t in texts):
        return {"error": "text (or texts, a list) is required"}, 400
    if sum(map(len, texts)) > MAX_CHARS:
        return {"error": f"text is over {MAX_CHARS} characters"}, 413
    pair = (d.get("from") or guess_lang(" ".join(texts)), to)
    if pair not in MODELS:
        return {"error": f"no translation from {pair[0]} to {pair[1]}"}, 400
    if single:
        return {"translation": translate(texts[0].strip(), to, pair[0]), "model": MODELS[pair]}
    return {"translations": _run([t.strip() for t in texts], pair), "model": MODELS[pair]}


if __name__ == "__main__":
    assert SPLIT.split("Sota alkoi 30. marraskuuta 1939. Se päättyi 13. maaliskuuta 1940.") == [
        "Sota alkoi 30. marraskuuta 1939.", "Se päättyi 13. maaliskuuta 1940."]     # years yes, day numbers no
    assert SPLIT.split("Sota alkoi talvella. Se päättyi keväällä.") == ["Sota alkoi talvella.", "Se päättyi keväällä."]
    assert guess_lang("Talvisota alkoi vuonna 1939, ja se päättyi keväällä.") == "fi"
    assert guess_lang("The Winter War began in 1939 and ended in the spring.") == "en"
    assert guess_lang("Vinterkriget började 1939 och var kort.") == "sv"
    print("split and language guess ok")
    import time
    t = time.time()
    en = translate("Valkoiset valtasivat Viipurin 29. huhtikuuta 1918. Punaisia kuoli 500–800.\nSota päättyi.")
    print(f"{time.time() - t:.1f} s: {en!r}")
    assert "1918" in en and "29" in en and "\n" in en      # dates kept (figures may be spelled out)
    assert "staged" in translate("Mainilan laukaukset olivat Neuvostoliiton lavastama tapahtuma."), "meaning lost"
    fi = _run(["The Winter War began on 30 November 1939.", "Finland lost about a tenth of its area."], ("en", "fi"))
    print("en -> fi:", fi)
    assert len(fi) == 2 and "1939" in fi[0]
    print("ok")
