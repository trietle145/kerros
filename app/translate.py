"""Machine translation of Finnish passages (owner: A, backend). Helsinki-NLP Opus-MT models run on
our own server: no API, no key, no cost per call, and the text never leaves the server.

    POST /api/translate  {"text": "...", "to": "en" | "sv"}  ->  {"translation", "model"}
    python -m app.translate      # self-check: the sentence split, then one real translation
"""
import re
import threading
from functools import lru_cache

from flask import Blueprint, request

bp = Blueprint("translate", __name__)
MODELS = {"en": "Helsinki-NLP/opus-mt-fi-en", "sv": "Helsinki-NLP/opus-mt-fi-sv"}
MAX_CHARS = 4000         # a passage is <= ~300 words; more would tie up the CPU
# A sentence ends at . ! ? after a letter or a 4-digit year, before a capital; never after a day
# number: split after the "30." of "30. marraskuuta" and the model sees fragments and invents dates.
SPLIT = re.compile(r"(?:(?<=[^\W\d][.!?])|(?<=\d{4}[.!?]))\s+(?=[A-ZÅÄÖ])")
_lock = threading.Lock()  # ponytail: one translation at a time on the 4-core server; a queue if busy


@lru_cache(maxsize=2)
def _model(to):
    from transformers import MarianMTModel, MarianTokenizer
    return MarianTokenizer.from_pretrained(MODELS[to]), MarianMTModel.from_pretrained(MODELS[to])


@lru_cache(maxsize=2000)
def translate(text, to="en"):
    """Finnish text -> en/sv, line breaks kept. Beam search (4): greedy decoding was twice as fast
    but lost meaning ("lavastama", staged -> "Soviet-style"). ~3 s for a typical passage, ~10 s
    for the longest, cached after."""
    tok, model = _model(to)
    lines = [SPLIT.split(line) for line in text.splitlines() if line.strip()]
    with _lock:
        out = model.generate(**tok([s for line in lines for s in line], return_tensors="pt",
                                   padding=True, truncation=True), num_beams=4, max_new_tokens=400)
    done = iter(tok.batch_decode(out, skip_special_tokens=True))
    return "\n".join(" ".join(next(done) for _ in line) for line in lines)


@bp.post("/api/translate")
def api():
    d = request.get_json(silent=True) or {}
    text, to = (d.get("text") or "").strip(), d.get("to", "en")
    if not text or to not in MODELS:
        return {"error": "text and to (en or sv) are required"}, 400
    if len(text) > MAX_CHARS:
        return {"error": f"text is over {MAX_CHARS} characters"}, 413
    return {"translation": translate(text, to), "model": MODELS[to]}


if __name__ == "__main__":
    assert SPLIT.split("Sota alkoi 30. marraskuuta 1939. Se päättyi 13. maaliskuuta 1940.") == [
        "Sota alkoi 30. marraskuuta 1939.", "Se päättyi 13. maaliskuuta 1940."]     # years yes, day numbers no
    assert SPLIT.split("Sota alkoi talvella. Se päättyi keväällä.") == ["Sota alkoi talvella.", "Se päättyi keväällä."]
    print("split ok")
    import time
    t = time.time()
    en = translate("Valkoiset valtasivat Viipurin 29. huhtikuuta 1918. Punaisia kuoli 500–800.\nSota päättyi.")
    print(f"{time.time() - t:.1f} s: {en!r}")
    assert "1918" in en and "29" in en and "\n" in en      # dates kept (figures may be spelled out)
    assert "staged" in translate("Mainilan laukaukset olivat Neuvostoliiton lavastama tapahtuma."), "meaning lost"
    print("ok")
