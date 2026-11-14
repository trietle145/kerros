"""Database connection for the app (shared file, frozen after 1.S)."""
from scripts.common import connect as _connect


def connect():
    """A new connection with the fixed vector search setting (CLAUDE.md: M=16, ef_search=80)."""
    con = _connect()
    con.cursor().execute("SET mhnsw_ef_search = 80")
    return con
