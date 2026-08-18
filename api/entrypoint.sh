#!/bin/sh
# The certificate comes from the certbot container, which may still be issuing it, and which
# replaces it every 60 days. uvicorn reads it once at start, so this script waits for the file
# and exits when it changes; the restart policy then brings the API back on the new certificate.

configured="${SSL_CERTFILE:-/certs/cert.pem}"
cert="$configured"
key="${SSL_KEYFILE:-/certs/key.pem}"

cert_stamp() {
  stat -Lc %Y "$configured" 2>/dev/null
}

wait_for_cert() {
  attempt=0
  while [ ! -f "$configured" ] && [ "$attempt" -lt 60 ]; do
    sleep 5
    attempt=$((attempt + 1))
  done
  [ -f "$configured" ] && return 0
  echo "entrypoint: $configured is missing, serving the self-signed pair instead"
  cert=/certs/cert.pem
  key=/certs/key.pem
}

exit_on_new_cert() {
  stamp=$(cert_stamp)
  while sleep 3600; do
    [ "$(cert_stamp)" != "$stamp" ] && break
  done
  echo "entrypoint: certificate changed, restarting"
  kill "$1"
}

wait_for_cert

uvicorn server:app --host 0.0.0.0 --port 8443 --ssl-keyfile "$key" --ssl-certfile "$cert" &
server=$!

exit_on_new_cert "$server" &

wait "$server"
