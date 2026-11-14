"""Embed each distinct passage text with the shared app.embed.embed() (task 1.A7).

    python scripts/embed_passages.py data/pilot/passages.parquet   # -> data/pilot/passage_vectors.parquet
    python scripts/embed_passages.py                               # data/passages.parquet, all of them
    modal run scripts/modal_embed.py                               # the same, embedded on a Modal GPU

Writes passage_vectors.parquet next to the input: text_hash, model, embedding (1024 float32,
normalised). Checks every hash against its embedding input first, so a changed input rule fails
loudly instead of producing vectors that no longer match their hashes.
"""
import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from build_passages import embedding_input
from common import ROOT

sys.path.insert(0, str(ROOT))        # for app.embed
from app.embed import MODEL, embed   # noqa: E402

CHUNK = 256


def main(src=None, embed_chunks=None):
    """embed_chunks: list of text chunks -> iterable of vector lists, in order (default: local CPU/GPU)."""
    src = Path(src or (sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "passages.parquet"))
    dst = src.with_name("passage_vectors.parquet")
    todo = {}
    for r in pq.read_table(src).to_pylist():
        todo.setdefault(r["text_hash"], embedding_input(r["title"], r["heading"], r["text"]))
    for h, text in todo.items():
        assert hashlib.sha256(text.encode("utf-8")).digest() == h, "hash does not match its input"

    hashes, inputs = list(todo), list(todo.values())
    del todo
    print(f"{len(inputs)} distinct texts to embed with {MODEL}", flush=True)
    start, done, writer = time.time(), 0, None
    chunks = [inputs[i:i + CHUNK] for i in range(0, len(inputs), CHUNK)]
    for vecs in (embed_chunks or (lambda cs: map(embed, cs)))(chunks):   # in order
        batch = pa.table({            # written as it arrives: 400k vectors never sit in memory
            "text_hash": pa.array(hashes[done:done + len(vecs)], pa.binary(32)),
            "model": pa.array([MODEL] * len(vecs)),
            "embedding": pa.FixedSizeListArray.from_arrays(
                pa.array(np.frombuffer(b"".join(vecs), "<f4")), 1024)})
        writer = writer or pq.ParquetWriter(dst, batch.schema)
        writer.write_table(batch)
        done, secs = done + len(vecs), time.time() - start
        if done % (CHUNK * 20) < CHUNK or done == len(inputs):
            print(f"{done}/{len(inputs)} in {secs / 60:.1f} min ({done / secs:.1f}/s), "
                  f"ETA {(len(inputs) - done) / (done / secs) / 60:.1f} min", flush=True)
    writer.close()
    print(f"written to {dst}")


if __name__ == "__main__":
    main()
