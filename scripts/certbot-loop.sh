#!/bin/sh
# Entrypoint of the certbot container: issue once, then renew twice a day.

: "${DOMAIN:?DOMAIN is not set}"
: "${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL is not set}"

issue() {
  certbot certonly --standalone --non-interactive --agree-tos --keep-until-expiring \
    -m "$LETSENCRYPT_EMAIL" -d "$DOMAIN"
}

# Retry slowly: Let's Encrypt counts failures per hour and a crash loop burns the quota.
while ! issue; do
  echo "certbot: issuing for $DOMAIN failed, retrying in 10 min"
  sleep 600
done

while sleep 43200; do
  certbot renew --standalone
done
