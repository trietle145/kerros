#!/usr/bin/env bash
# Public HTTPS for the app: Caddy in front of gunicorn (127.0.0.1:5000) with an automatic
# certificate; optionally one password for the whole site. Run on the server as root:
#
#   bash scripts/setup_public.sh <site>                     # open site
#   bash scripts/setup_public.sh <site> <user> <password>   # behind a password
#   bash scripts/setup_public.sh 135.181.8.213.compute.verda.run
#
# Needs inbound TCP 80 (certificate) and 443 (site) open in the Verda firewall. Rerun to add,
# change or drop the password. Model calls are capped in the app (ASK_HOURLY_PER_VISITOR per IP,
# ASK_DAILY_LIMIT overall). MariaDB stays private; app deploys don't touch Caddy.
set -euo pipefail
SITE=$1 USER_NAME=${2:-} PASS=${3:-}
command -v caddy > /dev/null || { apt-get update -q && apt-get install -y -q caddy; }
AUTH=""
if [ -n "$PASS" ]; then
	AUTH=$(printf '\tbasicauth {\n\t\t%s %s\n\t}' "$USER_NAME" "$(caddy hash-password --plaintext "$PASS")")
fi
cat > /etc/caddy/Caddyfile <<EOF
$SITE {
	encode gzip
$AUTH
	reverse_proxy 127.0.0.1:5000
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable --now caddy
systemctl reload caddy
echo "https://$SITE is live${USER_NAME:+ (user: $USER_NAME)}"
