"""The Flask app (shared file). Routes live in their owners' blueprints: backend (A) =
answer.py (/ask), history.py (/article...), graph.py (/api/graph), xlang.py (/api/xlang); frontend (B) = ask.py (pages).

    flask --app app.main run --debug
"""
from flask import Flask

from app import answer, ask, graph, history, xlang

app = Flask(__name__)
app.register_blueprint(ask.bp)
app.register_blueprint(history.bp)
app.register_blueprint(answer.bp)
app.register_blueprint(graph.bp)
app.register_blueprint(xlang.bp)
