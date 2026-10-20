#!/bin/bash
# Create a self-signed certificate covering localhost, hostname, and host IPs.
# Browsers will show a warning once; after "Proceed" the page is a secure context (GPS works).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CERT_DIR="${CERT_DIR:-$SCRIPT_DIR/../nginx/certs}"
DAYS="${DAYS:-825}"
CN="${TLS_CN:-odoo.local}"

mkdir -p "$CERT_DIR"

SAN_PARTS=("DNS:localhost" "DNS:debian" "DNS:${CN}")
# Extra public names, comma-separated: TLS_EXTRA_DNS=hrmkienviet.ddns.net
if [[ -n "${TLS_EXTRA_DNS:-}" ]]; then
  IFS=',' read -ra EXTRA_DNS <<< "$TLS_EXTRA_DNS"
  for name in "${EXTRA_DNS[@]}"; do
    name="${name// /}"
    [[ -n "$name" ]] && SAN_PARTS+=("DNS:${name}")
  done
fi
if HOSTNAME_SHORT="$(hostname -s 2>/dev/null)" && [[ -n "$HOSTNAME_SHORT" ]]; then
  SAN_PARTS+=("DNS:${HOSTNAME_SHORT}")
fi
if HOSTNAME_FQDN="$(hostname -f 2>/dev/null)" && [[ -n "$HOSTNAME_FQDN" ]]; then
  SAN_PARTS+=("DNS:${HOSTNAME_FQDN}")
fi

IPS=(127.0.0.1)
if command -v ip >/dev/null 2>&1; then
  while read -r addr; do
    case "$addr" in
      127.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*|169.254.*) continue ;;
    esac
    IPS+=("$addr")
  done < <(ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1)
fi

for ip in "${IPS[@]}"; do
  SAN_PARTS+=("IP:${ip}")
done

# Deduplicate while keeping order
SAN=""
declare -A SEEN=()
for part in "${SAN_PARTS[@]}"; do
  if [[ -z "${SEEN[$part]+x}" ]]; then
    SEEN[$part]=1
    SAN="${SAN:+$SAN,}${part}"
  fi
done

openssl req -x509 -newkey rsa:2048 -sha256 -days "$DAYS" -nodes \
  -keyout "$CERT_DIR/privkey.pem" \
  -out "$CERT_DIR/fullchain.pem" \
  -subj "/CN=${CN}" \
  -addext "subjectAltName=${SAN}" \
  -addext "basicConstraints=CA:FALSE" \
  -addext "keyUsage=digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"

chmod 600 "$CERT_DIR/privkey.pem"
chmod 644 "$CERT_DIR/fullchain.pem"

echo "Wrote $CERT_DIR/fullchain.pem"
echo "SAN: $SAN"
openssl x509 -in "$CERT_DIR/fullchain.pem" -noout -dates -ext subjectAltName
