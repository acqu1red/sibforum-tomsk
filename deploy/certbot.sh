#!/bin/sh
set -eu

# Compose overrides (e.g. renew --quiet) are passed straight to Certbot.
if [ "$#" -gt 0 ]; then
    exec certbot "$@"
fi
set -- certonly --webroot -w /var/lib/letsencrypt \
    -d "$DOMAIN" -d "$ADMIN_DOMAIN" --agree-tos --non-interactive
if [ -n "${TLS_EMAIL:-}" ]; then
    set -- "$@" --email "$TLS_EMAIL"
else
    set -- "$@" --register-unsafely-without-email
fi
exec certbot "$@"
