#!/bin/sh
set -e
# Generate Caddyfile from PROXY_DOMAIN: with domain => HTTPS + HTTP, without => :80 only
CADDYFILE="/etc/caddy/Caddyfile"
if [ -n "$PROXY_DOMAIN" ]; then
  cat > "$CADDYFILE" <<EOF
{$PROXY_DOMAIN} {
    reverse_proxy frontend:80
}
EOF
else
  cat > "$CADDYFILE" <<EOF
:80 {
    reverse_proxy frontend:80
}
EOF
fi
exec caddy run --config "$CADDYFILE" --adapter caddyfile
