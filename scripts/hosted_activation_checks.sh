#!/usr/bin/env bash
# Read-only readiness checks for Sweetfamily activation; safe to source without root.

sf_certificate_ready() {
    local directory=$1 domain
    shift
    [[ -s $directory/fullchain.pem && -s $directory/privkey.pem ]] || return 1
    openssl x509 -in "$directory/fullchain.pem" -noout -checkend 2592000 >/dev/null 2>&1 || return 1
    for domain in "$@"; do
        # x509 -checkhost can exit zero even on a mismatch; verify enforces the result.
        openssl verify -purpose sslserver -verify_hostname "$domain" \
            -untrusted "$directory/fullchain.pem" "$directory/fullchain.pem" \
            >/dev/null 2>&1 || return 1
    done
}

sf_wait_https() {
    local domain=$1 route=$2 directory=$3 port=${4:-443} timeout=${5:-60}
    local deadline=$((SECONDS + timeout)) status='' announced=false
    local -a routing=()
    if [[ $route == local ]]; then
        routing=(--resolve "$domain:$port:127.0.0.1")
    elif [[ $route != public ]]; then
        echo 'Unknown HTTPS verification route' >&2
        return 1
    fi
    while true; do
        # --resolve changes only the destination. SNI, hostname and CA validation stay on.
        # Never follow redirects or inherit an outgoing HTTP proxy for this health check.
        if status=$(curl --noproxy '*' --fail --silent --show-error \
            --connect-timeout 2 --max-time 3 "${routing[@]}" \
            --output "$directory/https-body" --write-out '%{http_code}' \
            "https://$domain:$port/health/ready" 2>"$directory/https-error") \
            && [[ $status == 200 ]] \
            && grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "$directory/https-body"; then
            return 0
        fi
        if (( SECONDS >= deadline )); then
            echo "HTTPS readiness timed out for $domain ($route, HTTP ${status:-unavailable})." >&2
            cat "$directory/https-error" >&2
            return 1
        fi
        if [[ $announced == false ]]; then
            echo "Waiting for nginx to serve validated HTTPS for $domain ($route, up to ${timeout}s)."
            announced=true
        fi
        sleep 1
    done
}

sf_wait_acme() {
    local domain=$1 probe=$2 directory=$3
    local deadline=$((SECONDS + 60))
    while true; do
        if curl --noproxy '*' --fail --silent --show-error \
            --connect-timeout 2 --max-time 3 --resolve "$domain:80:127.0.0.1" \
            "http://$domain/.well-known/acme-challenge/${probe##*/}" \
            >"$directory/acme-body" 2>"$directory/acme-error" \
            && cmp -s "$probe" "$directory/acme-body"; then
            return 0
        fi
        if (( SECONDS >= deadline )); then
            echo "ACME webroot readiness timed out for $domain." >&2
            cat "$directory/acme-error" >&2
            return 1
        fi
        sleep 1
    done
}
