#!/usr/bin/env bash
# Build Sunshine with a CUDA 12.x toolchain so NVENC works on the Tesla V100 (sm_70).
#
# Why: official Sunshine packages since 2026.914 are built with CUDA 13, which dropped Volta;
# their CUDA kernels fail on the V100 ("cudaErrorInsufficientDriver" with driver 550) and
# Sunshine silently falls back to libx264. Sunshine's CMake adds sm_70 by itself whenever the
# CUDA compiler is < 13 (cmake/compile_definitions/linux.cmake), so only the toolkit changes.
#
# Run as root on CT 144. Takes ~1h (CUDA download + build) and needs ~12 GB of disk.
#   deploy/sunshine/build-sunshine.sh [git-ref]   # default: the ref below
# Produces /opt/creative-suite/packages/sunshine_<version>+homelab.cuda12.9.sm70_amd64.deb,
# installs it and puts the package on hold so apt does not bring back an official build.
set -euo pipefail

REF="${1:-v2026.914.233613}"
SRC=/opt/creative-suite/src/sunshine
PKG_DIR=/opt/creative-suite/packages
CUDA_VERSION=12.9.1        # last CUDA line that still targets sm_70 and accepts GCC 14
CUDA_BUILD=575.57.08
JOBS=3                     # 8 GB container: more parallel cc1plus jobs thrash memory
export HOME=/root          # linux_build.sh installs nvm under $HOME

log() { printf '[sunshine-build] %s\n' "$*"; }

if [[ ! -d "$SRC/.git" ]]; then
    git clone https://github.com/LizardByte/Sunshine.git "$SRC"
fi
cd "$SRC"
git fetch --tags -q
git checkout -q "$REF"
# The LizardByte mirror of wayland-protocols does not serve the pinned commit; upstream does.
git config submodule.third-party/wayland-protocols.url https://gitlab.freedesktop.org/wayland/wayland-protocols.git
git submodule update --init --recursive --force -q

sed -i "s/^default_cuda_version=.*/default_cuda_version=\"$CUDA_VERSION\"/; s/^default_cuda_build=.*/default_cuda_build=\"$CUDA_BUILD\"/" \
    scripts/linux_build.sh

# Dependencies, CUDA toolkit (into build/cuda) and CMake configuration only: the script's own build
# step runs `ninja` without -j and ignores --num-processors.
log "deps + cmake"
./scripts/linux_build.sh --ubuntu-test-repo --step=deps
./scripts/linux_build.sh --ubuntu-test-repo --step=cmake

NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin | sort -V | tail -1)"
export PATH="$NODE_BIN:$SRC/build/cuda/bin:$PATH"   # the web UI needs nvm's Node, not Ubuntu's v12
log "reconfigure without tests (node $(node --version), nvcc $(nvcc --version | grep -o 'release [0-9.]*'))"
archs="$(cmake -B build -DBUILD_TESTS=OFF | sed -n 's/.*CUDA Architectures: //p')"
log "CUDA architectures: $archs"
[[ ";$archs;" == *";70;"* ]] || { log "sm_70 missing from the CUDA architectures, aborting"; exit 1; }

log "build (-j$JOBS)"
ninja -C build -j"$JOBS"
cpack -G DEB --config ./build/CPackConfig.cmake >/dev/null

# Give the package a version that sorts above the official build it replaces and says what it is.
deb="$(ls -t build/cpack_artifacts/*.deb | head -1)"
version="${REF#v}+homelab.cuda${CUDA_VERSION%.*}.sm70"
work="$(mktemp -d)"
dpkg-deb -R "$deb" "$work"
sed -i "s/^Version: .*/Version: $version/" "$work/DEBIAN/control"
chmod 0755 "$work"/DEBIAN/{preinst,postinst,prerm,postrm} 2>/dev/null || true
mkdir -p "$PKG_DIR"
out="$PKG_DIR/sunshine_${version}_amd64.deb"
dpkg-deb -b --root-owner-group "$work" "$out" >/dev/null
rm -rf "$work"

log "install $out"
apt-mark unhold sunshine >/dev/null 2>&1 || true
DEBIAN_FRONTEND=noninteractive apt-get install -y -q "$out"
apt-mark hold sunshine
systemctl restart sunshine
log "done: $(dpkg-query -W -f='${Version}' sunshine)"
