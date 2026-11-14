#!/usr/bin/env bash
# One-time setup of the shared server (fresh Ubuntu, Verda CPU instance). Idempotent: safe to rerun.
# Run inside tmux so a dropped SSH session doesn't stop the ~15 min load:
#   tmux new -s setup
#   curl -fsSL https://raw.githubusercontent.com/trietle145/LakeBandits_junction/a-data-time/scripts/server_setup.sh | bash
# Afterwards: copy passages.parquet + passage_vectors.parquet into ~/LakeBandits_junction/data/ and run
#   .venv/bin/python scripts/load_vectors.py
# MariaDB listens on 127.0.0.1 only; reach it with:  ssh -N -L 3307:127.0.0.1:3306 <user>@<server-ip>
set -euo pipefail
BRANCH=${BRANCH:-a-data-time}
SUDO=$([ "$(id -u)" = 0 ] || echo sudo)

command -v docker >/dev/null || curl -fsSL https://get.docker.com | $SUDO sh
$SUDO apt-get update -qq && $SUDO apt-get install -y -qq git python3-venv python3-dev gcc libmariadb-dev tmux >/dev/null

cd ~
[ -d LakeBandits_junction ] || git clone -q -b "$BRANCH" https://github.com/trietle145/LakeBandits_junction
cd LakeBandits_junction && git pull -q

if [ ! -f .env ]; then                      # random passwords, written once, never committed
  ROOTPW=$(openssl rand -hex 16); PW=$(openssl rand -hex 16)
  sed -e "s/^MARIADB_ROOT_PASSWORD=.*/MARIADB_ROOT_PASSWORD=$ROOTPW/" \
      -e "s/^MARIADB_USER=.*/MARIADB_USER=wiki/;  s/^MARIADB_PASSWORD=.*/MARIADB_PASSWORD=$PW/" \
      -e "s/^DB_USER=.*/DB_USER=wiki/;            s/^DB_PASSWORD=.*/DB_PASSWORD=$PW/" \
      -e "s/^INNODB_BUFFER_POOL=.*/INNODB_BUFFER_POOL=8G/; s/^MHNSW_CACHE=.*/MHNSW_CACHE=2G/" \
      .env.example > .env
fi
$SUDO docker compose up -d

if [ ! -d .venv ]; then                     # CPU-only torch: the CUDA build is GBs we don't need
  python3 -m venv .venv
  .venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
  .venv/bin/pip install -q -r requirements.txt
fi

for set in m s; do                          # same as README "Local setup"
  mkdir -p data/$set
  ( cd data/$set
    [ -f SHA256SUMS ] && sha256sum -c --quiet SHA256SUMS 2>/dev/null && continue
    curl -s https://api.github.com/repos/MariaDB/mariadb-wikipedia-datasets/releases/tags/$set-2026-10 \
      | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 | xargs -n1 curl -sSLO
    sha256sum -c --quiet SHA256SUMS )
done

until $SUDO docker compose exec -T db healthcheck.sh --connect >/dev/null 2>&1; do sleep 2; done
.venv/bin/python scripts/load_m.py | tee data/load_m.log | tail -1
.venv/bin/python scripts/load_m.py --verify 20 | tail -1
.venv/bin/python scripts/load_s.py > data/load_s.log && .venv/bin/python scripts/load_s.py --verify | tail -1
.venv/bin/python -m app.embed               # bge-m3 for questions; needs ~5 GB free while loading

echo "Done. Next: copy passages.parquet + passage_vectors.parquet into $PWD/data and run"
echo "  .venv/bin/python scripts/load_vectors.py"
