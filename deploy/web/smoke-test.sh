#!/usr/bin/env bash
# Check the browser (WASM) suite on its container, without going through the proxy.
#   /opt/creative-suite/repo/deploy/web/smoke-test.sh
set -uo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE_ROOT=/var/www/apps
DOMAIN=lan.devgiov.com
failures=0

check() {  # check DESCRIPTION COMMAND...
    local description="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS  $description"
    else
        echo "FAIL  $description"
        failures=$((failures + 1))
    fi
}

status_is() {  # status_is STATUS HOST PATH
    [[ "$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $2" "http://127.0.0.1$3")" == "$1" ]]
}

wasm_ok() {  # wasm_ok HOST PATH: right MIME type, compressed when the client accepts it
    local headers
    headers="$(curl -s -D - -o /dev/null -H "Host: $1" -H 'Accept-Encoding: gzip' "http://127.0.0.1$2")"
    grep -qi '^content-type: application/wasm' <<<"$headers" && grep -qi '^content-encoding: gzip' <<<"$headers"
}

check "nginx active" systemctl is-active nginx
check "landing page" status_is 200 "apps.$DOMAIN" /
check "unknown host refused" bash -c "! curl -s -m 5 -H 'Host: other.example' http://127.0.0.1/"
check "hidden files hidden" status_is 404 "gridcraft.$DOMAIN" /.htaccess

while read -r app _ version _; do
    host="$app.$DOMAIN"
    check "$app $version installed" test "$(readlink -f "$SITE_ROOT/$app")" = "/opt/craft-web/releases/$app-$version"
    check "$app page" status_is 200 "$host" /
    wasm="$(cd "$SITE_ROOT/$app/" && find . -maxdepth 1 -name '*.wasm' | head -1)"
    if [[ -n "$wasm" ]]; then
        check "$app wasm served" wasm_ok "$host" "/${wasm#./}"
    fi
done < <(python3 "$WEB_DIR/webapps.py" list)

if ((failures)); then
    echo
    echo "$failures check(s) failed"
    exit 1
fi
echo
echo "all checks passed"
