"""bge-m3 vectors for passages *and* questions (shared file, frozen after 1.S).
One function for both, so the two can never be embedded with different settings.

    python -m app.embed          # self-check: downloads the model once (~2.3 GB, into HF_HOME)
"""
from functools import lru_cache

MODEL = "BAAI/bge-m3"      # same model as the shipped S vectors
REVISION = "5617a9f61b028005a4858fdac845db406aefb181"   # pinned: every machine, same files
MAX_TOKENS = 1024          # a 300-word Finnish passage is ~600 tokens


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer   # slow import: only when embedding
    # Needs ~5 GB free memory while loading (2.3 GB fp32 weights, read via pytorch_model.bin).
    # Short of memory, loading fails with misleading errors ("Unrecognized processing class",
    # "memory allocation ... failed", a segfault): free memory, don't debug the model.
    try:   # cache first: no network on load, works offline
        m = SentenceTransformer(MODEL, revision=REVISION, local_files_only=True)
    except (OSError, ValueError):   # not cached yet: download once
        m = SentenceTransformer(MODEL, revision=REVISION)
    m.max_seq_length = MAX_TOKENS
    return m


def embed(texts, batch_size=16):
    """Normalised dense vectors, as the raw bytes MariaDB's VECTOR(1024) takes (1024 x float32 LE)."""
    vecs = _model().encode(list(texts), batch_size=batch_size, normalize_embeddings=True)
    return [v.astype("<f4").tobytes() for v in vecs]


if __name__ == "__main__":
    import struct
    a, b, c = (struct.unpack("<1024f", v) for v in
               embed(["Talvisota alkoi 1939.", "Talvisota alkoi vuonna 1939.", "Banaanikakku resepti"]))
    cos = lambda x, y: sum(i * j for i, j in zip(x, y))
    assert abs(cos(a, a) - 1) < 1e-3, "not normalised"
    assert cos(a, b) > cos(a, c), "similar sentences should be closer"
    print(f"ok: 4096 bytes per vector, similar {cos(a, b):.3f} > unrelated {cos(a, c):.3f}")
