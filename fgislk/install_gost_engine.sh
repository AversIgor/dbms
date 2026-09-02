#!/usr/bin/env bash
# gost-engine v3.0.3 для OpenSSL 3.0.x (Ubuntu 22.04/24.04).
# master требует OpenSSL ≥ 3.4 — на Noble/Jammy не соберётся.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "нужен root: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y build-essential cmake git pkg-config libssl-dev

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
cd "$WORKDIR"
git clone https://github.com/gost-engine/engine.git
cd engine
git fetch --tags
git checkout v3.0.3
git submodule update --init --recursive

cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DOPENSSL_ROOT_DIR=/usr
cmake --build build -j"$(nproc)"
cmake --install build

SO=""
for p in \
  /usr/lib/x86_64-linux-gnu/engines-3/gost.so \
  /usr/lib/aarch64-linux-gnu/engines-3/gost.so \
  /usr/lib/engines-3/gost.so
do
  if [[ -f "$p" ]]; then
    SO=$p
    break
  fi
done
if [[ -z "$SO" ]]; then
  echo "gost.so не найден после установки" >&2
  exit 1
fi

CNF=/etc/ssl/fgislk-openssl-gost.cnf
cat > "$CNF" << EOF
openssl_conf = openssl_def

[openssl_def]
engines = engine_section

[engine_section]
gost = gost_section

[gost_section]
engine_id = gost
dynamic_path = $SO
default_algorithms = ALL
init = 1
EOF

OPENSSL_CONF=$CNF openssl engine -t gost
echo "OK gost.so=$SO"
echo "OK OPENSSL_CONF=$CNF"
