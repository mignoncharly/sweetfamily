#!/usr/bin/env bash
# Sweetfamily staging activation: only the two named domains and project user units.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
if [[ $(id -u) != 0 ]]; then
    echo 'Administrator access required: run this script with sudo.' >&2
    exit 1
fi
project=/home/mignon/apps/sweetfamily
owner=mignon
owner_uid=$(id -u "$owner")
portal=sweetfamily.gestionatech.de
vault=vault.sweetfamily.gestionatech.de
address=217.154.166.155
site=/etc/nginx/sites-available/sweetfamily-staging
link=/etc/nginx/sites-enabled/sweetfamily-staging
webroot=/var/lib/sweetfamily-acme
cert=/etc/letsencrypt/live/sweetfamily.gestionatech.de
marker='# Managed exclusively by Sweetfamily staging activation.'
work=$(mktemp -d /tmp/sweetfamily-activate.XXXXXX)
changed=false
had_site=false
had_link=false
finished=false
cleanup() {
    if [[ $changed == true && $finished == false ]]; then
        if [[ $had_site == true ]]; then cp "$work/previous-site" "$site"; else rm -f "$site"; fi
        if [[ $had_link == false ]]; then rm -f "$link"; fi
        if nginx -t; then systemctl reload nginx; fi
        echo 'Activation did not complete; the previous nginx site state was restored.' >&2
    fi
    rm -rf "$work"
}
trap cleanup EXIT
as_owner() {
    runuser -u "$owner" -- env XDG_RUNTIME_DIR="/run/user/$owner_uid" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$owner_uid/bus" "$@"
}
local_dns_matches() {
    getent ahostsv4 "$1" | awk '{print $1}' | sort -u | grep -Fxq "$address"
}
for domain in "$portal" "$vault"; do
    if ! local_dns_matches "$domain"; then
        # A newly created record may already be public while the server's provider
        # retains an older NXDOMAIN. Wait without changing shared DNS configuration.
        if dig @1.1.1.1 +time=2 +tries=1 +short "$domain" A | grep -Fxq "$address"; then
            echo "Public DNS is correct for $domain; waiting up to 6 minutes for this server's DNS cache."
            deadline=$((SECONDS + 360))
            attempts=0
            until local_dns_matches "$domain"; do
                if (( SECONDS >= deadline )); then break; fi
                sleep 10
                attempts=$((attempts + 1))
                if (( attempts % 6 == 0 )); then
                    echo "Still waiting for the server resolver: $domain"
                fi
            done
        fi
        if ! local_dns_matches "$domain"; then
            echo "DNS not ready on this server: A $domain must resolve to $address" >&2
            echo "No nginx changes were made. Check DNS or retry after cached negative answers expire." >&2
            exit 2
        fi
    fi
    if [[ -n $(dig +short AAAA "$domain") ]]; then
        echo "Review the IPv6 record for $domain before activation; this host has no public IPv6." >&2
        exit 2
    fi
done
if [[ -e $site ]]; then
    grep -Fxq "$marker" "$site" || { echo 'Refusing to replace an unmanaged site' >&2; exit 1; }
    cp "$site" "$work/previous-site"
    had_site=true
fi
if [[ -L $link ]]; then
    [[ $(readlink -f "$link") == "$site" ]] || { echo 'Unexpected enabled site target' >&2; exit 1; }
    had_link=true
elif [[ -e $link ]]; then
    echo 'Refusing to replace a non-symlink enabled site' >&2
    exit 1
fi
nginx -t
before_pid=$(systemctl show gtech -p MainPID --value)
before_config=$(sha256sum /etc/nginx/sites-available/gtech | awk '{print $1}')
for role in control vault; do
    as_owner systemctl --user is-active --quiet "sweetfamily-staging-$role-web.service"
    port=8101
    domain=$portal
    if [[ $role == vault ]]; then port=8102; domain=$vault; fi
    curl --fail --silent --show-error --max-time 10 \
        -H "Host: $domain" -H 'X-Forwarded-Proto: https' \
        "http://127.0.0.1:$port/health/ready" >/dev/null
done
install -d -m 0755 "$webroot/.well-known/acme-challenge"
{
    echo "$marker"
    for domain in "$portal" "$vault"; do
        cat <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $domain;
    access_log off;
    error_log /var/log/nginx/sweetfamily-staging-error.log crit;
    location ^~ /.well-known/acme-challenge/ { root $webroot; default_type text/plain; }
    location / { return 503; }
}
EOF
    done
} > "$work/http.conf"
install -m 0644 "$work/http.conf" "$site"
changed=true
if [[ $had_link == false ]]; then ln -s "$site" "$link"; fi
nginx -t
systemctl reload nginx
certbot certonly --webroot --webroot-path "$webroot" \
    --cert-name "$portal" -d "$portal" -d "$vault" \
    --non-interactive --agree-tos --register-unsafely-without-email
install -m 0644 "$project/infra/hosted/sweetfamily.conf" "$site"
nginx -t
systemctl reload nginx
for domain in "$portal" "$vault"; do
    curl --fail --silent --show-error --max-time 15 "https://$domain/health/ready" >/dev/null
done
# Only these certificates trigger this hook; other applications' hooks are untouched.
hook=/etc/letsencrypt/renewal-hooks/deploy/sweetfamily-staging-reload
if [[ -e $hook ]] && ! grep -Fxq "$marker" "$hook"; then
    echo 'Refusing to replace an unmanaged renewal hook' >&2
    exit 1
fi
install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat > "$work/renew-hook" <<'EOF'
#!/bin/sh
# Managed exclusively by Sweetfamily staging activation.
case " ${RENEWED_DOMAINS:-} " in
  *" sweetfamily.gestionatech.de "*|*" vault.sweetfamily.gestionatech.de "*)
    /usr/sbin/nginx -t && /usr/bin/systemctl reload nginx ;;
esac
EOF
install -m 0755 "$work/renew-hook" "$hook"
loginctl enable-linger "$owner"
for role in control vault; do
    for component in db web worker; do
        as_owner systemctl --user enable "sweetfamily-staging-$role-$component.service"
    done
done
systemctl is-active --quiet gtech
[[ $(systemctl show gtech -p MainPID --value) == "$before_pid" ]]
[[ $(sha256sum /etc/nginx/sites-available/gtech | awk '{print $1}') == "$before_config" ]]
finished=true
echo "HTTPS staging active: https://$portal and https://$vault"
echo 'Real email remains disabled. Independent-vault and production qualification remain open.'
