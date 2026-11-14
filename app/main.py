"""The Flask app (shared file). Routes live in their owners' blueprints: backend (A) =
answer.py (/ask) and history.py (/article...); frontend (B) = ask.py (pages).

    flask --app app.main run --debug
"""
from flask import Flask

from app import answer, ask, history

app = Flask(__name__)
app.register_blueprint(ask.bp)
app.register_blueprint(history.bp)
app.register_blueprint(answer.bp)
