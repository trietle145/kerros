"""The Flask app (shared file, frozen after 1.S). Routes live in their owners' blueprints:
ask.py (B) and history.py (A).

    flask --app app.main run --debug
"""
from flask import Flask

from app import ask, history

app = Flask(__name__)
app.register_blueprint(ask.bp)
app.register_blueprint(history.bp)
