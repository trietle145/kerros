"""Run embed_passages.py with the embedding on a Modal GPU (task 1.A7). Everything else (hashes,
the hash check, writing passage_vectors.parquet) runs locally; only app.embed.embed() is remote,
so the vectors come from exactly the code that embeds questions.

    pip install modal && python -m modal setup                       # once
    modal run scripts/modal_embed.py --src data/pilot/passages.parquet   # pilot: 163 passages
    modal run scripts/modal_embed.py                                 # all ~66k passages

GPU = CPU check (1.A7): embed the pilot both ways and compare; on 2026-11-14 all 163 vectors had
cosine 1.00000. (Loading the model locally inside `modal run` fails, so it is not done here.)
"""
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]     # local: app.embed, embed_passages


def _download():
    from sentence_transformers import SentenceTransformer
    SentenceTransformer("BAAI/bge-m3", revision="5617a9f61b028005a4858fdac845db406aefb181")  # = app/embed.py


image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("sentence-transformers", "numpy")
         .run_function(_download)                      # bake the 2.3 GB model into the image
         .add_local_python_source("app"))
app = modal.App("lakebandits-embed", image=image)


@app.function(gpu="A10G", timeout=1800, max_containers=4)
def embed_remote(texts):
    from app.embed import embed
    return embed(texts, batch_size=32)


@app.local_entrypoint()
def main(src: str = str(ROOT / "data" / "passages.parquet")):
    import embed_passages
    embed_passages.main(src, embed_chunks=embed_remote.map)
