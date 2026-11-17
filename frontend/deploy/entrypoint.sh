#!/bin/sh
set -eu

: "${NEXUS_BASIC_AUTH_USER:?Set NEXUS_BASIC_AUTH_USER in the root .env file}"
: "${NEXUS_BASIC_AUTH_PASSWORD:?Set NEXUS_BASIC_AUTH_PASSWORD in the root .env file}"

if [ "${#NEXUS_BASIC_AUTH_PASSWORD}" -lt 16 ]; then
  echo "NEXUS_BASIC_AUTH_PASSWORD must contain at least 16 characters." >&2
  exit 1
fi

printf '%s\n' "$NEXUS_BASIC_AUTH_PASSWORD" | \
  htpasswd -i -B -c /etc/nginx/.htpasswd "$NEXUS_BASIC_AUTH_USER" >/dev/null

exec nginx -g 'daemon off;'
