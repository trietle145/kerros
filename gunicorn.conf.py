"""Production server for the app (backend, A).

    gunicorn -c gunicorn.conf.py app.main:app

One worker (bge-m3 is ~2.3 GB per process, the server has 16 GB shared with MariaDB) with
threads for concurrent requests; the model is loaded before the first request, so nobody waits
the ~13 s cold start.
"""
bind = "127.0.0.1:5000"      # never public directly: Caddy (HTTPS) or an SSH tunnel sits in front
workers = 1
threads = 8
timeout = 120                # a then-vs-now answer can take ~15 s; leave room


def post_worker_init(worker):
    from app.embed import embed
    from app.graph import link_index
    embed(["warm up"])
    link_index()                 # ~3 s: the wiki-link index behind /api/graph
    worker.log.info("bge-m3 loaded, link index built")
