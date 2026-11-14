#!/usr/bin/env bash
# Public HTTPS for the app: Caddy in front of gunicorn (127.0.0.1:5000) with an automatic
# certificate and one password for the whole site. Run on the server as root:
#
#   bash scripts/setup_public.sh <site> <user> <password>
#   bash scripts/setup_public.sh 135.181.8.213.compute.verda.run judge 'a long passphrase'
#
# Needs inbound TCP 80 (certificate) and 443 (site) open in the Verda firewall. Rerun to change
# the password. MariaDB stays private; app deploys don't touch Caddy (restart_app.sh as before).
set -euo pipefail
SITE=$1 USER_NAME=$2 PASS=$3
command -v caddy > /dev/null || { apt-get update -q && apt-get install -y -q caddy; }
HASH=$(caddy hash-password --plaintext "$PASS")
cat > /etc/caddy/Caddyfile <<EOF
$SITE {
	encode gzip
	basicauth {
		$USER_NAME $HASH
	}
	reverse_proxy 127.0.0.1:5000
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable --now caddy
systemctl reload caddy
echo "https://$SITE is live (user: $USER_NAME)"
