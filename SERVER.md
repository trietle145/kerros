# Connecting to the shared database server

The team's MariaDB runs on a rented server (Verda, Finland). It holds everything already
loaded, so you don't need your own database to work on search, answers or the app:

| Table | Rows | What |
| --- | --- | --- |
| `passage` | 66,642 | The chunks: title, heading, clean text, `page_id`, `rev_id`, `text_hash`, FULLTEXT index |
| `passage_vector` | 66,642 | bge-m3 vectors (`VECTOR(1024)`, index M=16, cosine), joined on `text_hash` |
| `article_vector` | 29,460 | Dataset S article vectors (fi, sv, en) |
| `article` | 862,076 versions | Full edit history (system-versioned, 19,742 current rows) |

The database is **not** open to the internet. You reach it through an SSH tunnel: your
laptop's port 3307 is forwarded to MariaDB on the server. You need two things from Triet: your
SSH key added to the server, and a database login.

## 1. Send Triet your SSH public key (once)

Check whether you have one:

```bash
cat ~/.ssh/id_ed25519.pub                 # macOS / Linux
type $HOME\.ssh\id_ed25519.pub            # Windows PowerShell
```

If the file doesn't exist, create it (press Enter at each question), then run the line above:

```bash
ssh-keygen -t ed25519
```

Send Triet the whole line it prints (starts with `ssh-ed25519`). It's the **public** half and is
safe to share. Never send the file without `.pub`.

Triet then adds the key and sends you your **database user name and password** in a direct
message. They are never written into the repo.

## 2. Check that SSH works

```bash
ssh root@135.181.8.213 "echo ok"
```

The first time it asks `Are you sure you want to continue connecting (yes/no)?`; type `yes`.
Seeing `ok` means your key works. This logs you in as root on the team server: look, don't
change anything there (no `docker` commands, no reloads) without asking Triet.

## 3. Open the tunnel (every time you work)

Leave this running in its own terminal. It prints nothing; that's normal:

```bash
ssh -N -L 3307:127.0.0.1:3306 root@135.181.8.213
```

If port 3307 is already used on your laptop (for example by your own local MariaDB), use
another local port, such as `-L 3308:127.0.0.1:3306`, and put that port in `.env` below.

## 4. Point the code at it

In your `.env` (copy `.env.example` if you don't have one; it is git-ignored):

```
DB_HOST=127.0.0.1
DB_PORT=3307
DB_USER=<user name from Triet>
DB_PASSWORD=<password from Triet>
DB_NAME=wiki
```

## 5. Check it works

From the repo root, with the tunnel open and your `.venv` active:

```bash
python -c "from app.db import connect; c = connect().cursor(); c.execute('SELECT COUNT(*) FROM passage'); print(c.fetchone()[0])"
```

It should print `66642`. A vector search to try:

```bash
python -c "
from app.db import connect; from app.embed import embed
c = connect().cursor()
c.execute('''SELECT p.title, p.heading FROM (SELECT text_hash, VEC_DISTANCE_COSINE(embedding, ?) d
             FROM passage_vector ORDER BY d LIMIT 5) v JOIN passage p USING (text_hash) ORDER BY d''',
          (embed(['Mitä tapahtui Mainilassa 1939?'])[0],))
print(*c.fetchall(), sep='\n')"
```

The first result should be *Mainilan laukaukset*. The model (`embed()`) runs on your laptop and
needs about 5 GB of free memory while it loads; close heavy programs if it fails with strange
errors such as "Unrecognized processing class".

## Good to know

- **Your login is read-only** (SELECT). That covers search, answers and the app. If you need
  to write (a table of your own, eval results), ask Triet for a write grant.
- **Switching back to a local database** is just `.env`: `DB_PORT` of your local MariaDB and
  its login. Nothing else in the code changes.
- **The first searches after a server restart are slow** (0.3–0.5 s) while the vector index
  loads into memory; after that ~10–20 ms.
- **Wikipedia text is CC BY-SA:** anything shown in the app links back to its version
  (`https://fi.wikipedia.org/?oldid=<rev_id>`).

## If something fails

| You see | Meaning | Fix |
| --- | --- | --- |
| `Permission denied (publickey)` | Your key isn't on the server yet | Send Triet your `.pub` line (step 1) |
| `Can't connect to server on '127.0.0.1'` | The tunnel isn't open | Start step 3 and leave it running |
| `bind ... Address already in use` | Port 3307 is taken on your laptop | Use `-L 3308:...` and `DB_PORT=3308` |
| `Access denied for user` | Wrong user name or password in `.env` | Check the values Triet sent |
| The tunnel closes after a while | The connection went idle | Add `-o ServerAliveInterval=60` to the step 3 command |
