"""Page routes (owner: B, frontend). Pages only: data comes from the JSON API (answer.py,
history.py, graph.py, insights.py), see docs/frontend.md."""
import os
import re
import urllib.error
import urllib.request

from flask import Blueprint, Response, render_template, request

bp = Blueprint("ask", __name__)


@bp.get("/")
def index():
    return render_template("ask.html")


@bp.get("/graph/<int:page_id>")
def graph(page_id):
    return render_template("graph.html", page_id=page_id, q=request.args.get("q", ""))


@bp.get("/drift")
def drift():
    return render_template("drift.html")


@bp.get("/tools")
def tools():
    return render_template("tools.html")


@bp.app_errorhandler(404)
@bp.app_errorhandler(500)
def error(e):
    """Pages get a styled error with a way back; JSON routes keep their JSON errors."""
    code = getattr(e, "code", 500)
    if request.path.startswith(("/api/", "/ask")) or request.accept_mimetypes.best == "application/json":
        return {"error": str(e)}, code
    return render_template("error.html", code=code), code


USER_LINK = re.compile(r"\[\[(?:Erikoissivu:Muokkaukset/|Toiminnot:Muokkaukset/|Special:Contributions/|Käyttäjä:|User:|"
                       r"Keskustelu käyttäjästä:|User talk:)[^\]]*\]\]", re.I)
USER_WORD = re.compile(r"\b(käyttäjän|käyttäjältä|käyttäjälle|käyttäjä|by|user)\s+(?!…)[^\s,.;:()]+", re.I)


@bp.app_template_filter("no_names")
def no_names(comment):
    """Edit summaries often name the reverted editor ("Kumottu käyttäjän X muokkaus"): the UI shows
    patterns, never names (CLAUDE.md boundaries), so user links and the word after "käyttäjän" go."""
    c = USER_LINK.sub("…", comment or "")
    c = USER_WORD.sub(lambda m: m.group(1) + " …", c)
    return re.sub(r"\(\s*…\s*\)", "", re.sub(r"(…\s*)+", "… ", c)).strip()


# Dev only: a laptop has the database tunnel but no model and no LLM key (CLAUDE.md: the key lives on
# the server). With ASK_UPSTREAM=http://127.0.0.1:5000 (the tunnel to the server's app) the routes that
# need them are answered by the server; everything else runs locally. Unset = no effect.
UPSTREAM = os.environ.get("ASK_UPSTREAM", "").rstrip("/")
FORWARD = ("/ask", "/api/related", "/api/cite")      # the routes that need the embedding model


@bp.before_app_request
def forward():
    if not UPSTREAM or request.path not in FORWARD:      # /ask/l is not forwarded: the server's app may not have it
        return None
    try:
        with urllib.request.urlopen(f"{UPSTREAM}{request.path}?{request.query_string.decode()}", timeout=90) as r:
            return Response(r.read(), r.status, content_type=r.headers.get("Content-Type", "application/json"))
    except urllib.error.HTTPError as e:                  # the server's own JSON error (400, 422, 500) passes through
        return Response(e.read(), e.code, content_type=e.headers.get("Content-Type", "application/json"))
    except Exception as e:
        return {"error": f"the server behind ASK_UPSTREAM did not answer: {type(e).__name__}: {e}"}, 502
