#!/usr/bin/env bash
# Install the browser (WASM) suite from deploy/web/apps.tsv on its container (CT 151).
# Idempotent: run as root after every `git pull`.
#   /opt/creative-suite/repo/deploy/web/install.sh
# Only apps whose version changed are downloaded; each switches atomically to its new release.
set -euo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASES=/opt/craft-web/releases
SITE_ROOT=/var/www/apps
PACKAGES=(nginx unzip curl python3)

log() { printf '[web-install] %s\n' "$*"; }

missing=()
for pkg in "${PACKAGES[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if ((${#missing[@]})); then
    log "apt install ${missing[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
fi

fetch_release() {  # fetch_release APP OWNER VERSION SHA256 DEST
    local app="$1" owner="$2" version="$3" sha256="$4" dest="$5" tmp
    tmp="$(mktemp -d "$RELEASES/.tmp.XXXXXX")"
    trap 'rm -rf "$tmp"' RETURN
    log "$app $version: download"
    curl -fsSL --retry 3 -o "$tmp/bundle.zip" \
        "https://github.com/$owner/$app/releases/download/v$version/$app-web-$version.zip"
    echo "$sha256  $tmp/bundle.zip" | sha256sum -c --quiet -
    unzip -q "$tmp/bundle.zip" -d "$tmp/unpacked"
    local site="$tmp/unpacked/$app-web-$version"
    [[ -f "$site/index.html" ]] || { log "$app: no index.html in the bundle"; return 1; }
    # PhotoCraft 0.19: the glue in app/ imports ./snippets, but the zip has that folder one level up.
    if [[ -d "$site/snippets" && -d "$site/app" && ! -e "$site/app/snippets" ]]; then
        cp -r "$site/snippets" "$site/app/snippets"
    fi
    find "$site" -type f \( -name '*.wasm' -o -name '*.js' \) -size +1k -exec gzip -kf -9 {} +
    chmod -R a+rX "$site"
    mv "$site" "$dest"
}

mkdir -p "$RELEASES" "$SITE_ROOT"
failed=()
while read -r app owner version sha256; do
    current="$RELEASES/$app-$version"
    if [[ ! -d "$current" ]] && ! fetch_release "$app" "$owner" "$version" "$sha256" "$current"; then
        log "$app $version: FAILED, keeping the previous release"
        failed+=("$app")
        continue
    fi
    ln -sfn "$current" "$SITE_ROOT/.$app.new"
    mv -T "$SITE_ROOT/.$app.new" "$SITE_ROOT/$app"
    find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -name "$app-*" ! -path "$current" -exec rm -rf {} +
done < <(python3 "$WEB_DIR/webapps.py" list)

log "landing page"
mkdir -p "$SITE_ROOT/apps"
python3 "$WEB_DIR/webapps.py" landing "$SITE_ROOT/apps/index.html"

log "nginx"
install -m 0644 "$WEB_DIR/nginx.conf" /etc/nginx/sites-available/craft-web
ln -sfn /etc/nginx/sites-available/craft-web /etc/nginx/sites-enabled/craft-web
rm -f /etc/nginx/sites-enabled/default
nginx -t -q
systemctl enable -q nginx
systemctl reload-or-restart nginx

log "finished; failed: ${failed[*]:-none}"
((${#failed[@]} == 0))
