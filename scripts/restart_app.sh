#!/usr/bin/env bash
# Restart the app on the server (run from the repo root). gunicorn treats SIGHUP (sent when its
# tmux session is killed) as "reload", so stop it with SIGTERM first, then start one copy.
cd "$(dirname "$0")/.."
pkill -TERM -f "gunicorn -c gunicorn.conf.py" && sleep 3
tmux kill-session -t web 2>/dev/null
tmux new -d -s web ".venv/bin/gunicorn -c gunicorn.conf.py app.main:app > /root/web.log 2>&1"
for i in $(seq 1 60); do grep -q "link index built" /root/web.log && break; sleep 2; done
grep -aE "Listening|link index built|ERROR" /root/web.log
