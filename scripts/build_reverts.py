"""Fill `revert_event` from the versioned `article` table, once after loading (task 2.A1).

    python scripts/build_reverts.py              # rebuild the table (TRUNCATE + one INSERT ... SELECT)
    python scripts/build_reverts.py --verify 30  # recompute 30 random articles in Python and compare

A revert is a version whose text (sha1) already existed earlier in the same article, with other
versions in between: those in-between versions were undone. Versions with no sha1 (hidden by
admins) and blanked pages are never counted as the reverting version; restoring text after a
blanking still counts. Known limit: exact text only, so partial reverts are missed.
"""
import argparse
import random
import sys
import time

from common import connect

# rn numbers every version of an article; LEAD gives the version after each one. Within the
# versions sharing one sha1, LAG finds the previous time this exact text existed. The undone
# edits are the ones from just after that earlier version up to just before this one.
BUILD = """
INSERT INTO revert_event
SELECT page_id, rev_id, row_start, user, anonymous,
       prev_rev_id, prev_end, rn - prev_rn - 1, prev_next_user, prev_next_anonymous
FROM (
  SELECT v.*, LAG(rev_id) OVER w AS prev_rev_id, LAG(row_end) OVER w AS prev_end,
              LAG(rn) OVER w AS prev_rn, LAG(next_user) OVER w AS prev_next_user,
              LAG(next_anonymous) OVER w AS prev_next_anonymous
  FROM (SELECT page_id, rev_id, user, anonymous, sha1, len, row_start, row_end,
               ROW_NUMBER() OVER p AS rn, LEAD(user) OVER p AS next_user,
               LEAD(anonymous) OVER p AS next_anonymous
        FROM article FOR SYSTEM_TIME ALL
        WINDOW p AS (PARTITION BY page_id ORDER BY row_start)) v
  WINDOW w AS (PARTITION BY page_id, sha1 ORDER BY row_start)
) x
WHERE rn - prev_rn > 1 AND sha1 <> '' AND len > 0"""


def build(con, cur):
    start = time.time()
    cur.execute("TRUNCATE TABLE revert_event")
    cur.execute(BUILD)
    con.commit()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT page_id), SUM(undone_anonymous) FROM revert_event")
    n, pages, anon = cur.fetchone()
    print(f"{n} reverts in {pages} articles ({anon} undid an anonymous edit), "
          f"{time.time() - start:.0f} s")
    cur.execute("SELECT COUNT(*) FROM revert_event WHERE page_id = 1256")
    print(f"Talvisota: {cur.fetchone()[0]} reverts (SVT starter README: 328)")


def expected(versions):
    """The same rule in plain Python: versions = [(rev_id, sha1, len, user, anonymous)] by time."""
    out, last = set(), {}
    for i, (rev, sha1, length, _, _) in enumerate(versions):
        j = last.get(sha1)
        if j is not None and i - j > 1 and sha1 and length:
            out.add((rev, versions[j][0], i - j - 1, versions[j + 1][3]))
        last[sha1] = i
    return out


def verify(cur, n):
    cur.execute("SELECT DISTINCT page_id FROM revert_event")
    pages = random.sample([p for (p,) in cur.fetchall()], n) + [1256]
    bad = 0
    for page_id in pages:
        cur.execute("SELECT rev_id, sha1, len, user, anonymous FROM article FOR SYSTEM_TIME ALL "
                    "WHERE page_id = ? ORDER BY row_start", (page_id,))
        want = expected(cur.fetchall())
        cur.execute("SELECT rev_id, restored_rev_id, undone_edits, undone_user FROM revert_event "
                    "WHERE page_id = ?", (page_id,))
        got = set(cur.fetchall())
        bad += got != want
        if got != want:
            print(f"  {page_id}: table {len(got)}, python {len(want)} MISMATCH")
    print(f"verify: {len(pages)} articles, " + ("all ok" if not bad else f"{bad} mismatches"))
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", type=int, metavar="N", help="compare N random articles and exit")
    args = ap.parse_args()
    con = connect()
    cur = con.cursor()
    if args.verify:
        sys.exit(0 if verify(cur, args.verify) else 1)
    build(con, cur)


if __name__ == "__main__":
    main()
