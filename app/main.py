"""The Flask app (shared file). Routes live in their owners' blueprints: backend (A) =
answer.py (/ask), history.py (/article...), graph.py (/api/graph), xlang.py (/api/xlang), translate.py (/api/translate), insights.py (health, rewind, radar, explain, /ask/l); frontend (B) = ask.py (pages).

    flask --app app.main run --debug
"""
from flask import Flask

from app import answer, ask, graph, history, insights, translate, xlang

app = Flask(__name__)
app.register_blueprint(ask.bp)
app.register_blueprint(history.bp)
app.register_blueprint(answer.bp)
app.register_blueprint(graph.bp)
app.register_blueprint(xlang.bp)
app.register_blueprint(translate.bp)
app.register_blueprint(insights.bp)
