#!/usr/bin/env bash
# Проверка TLS к ФГИС ЛК с Ubuntu. Пароль в вывод не пишет.
# Запуск из корня репозитория: bash fgislk/check_fgis_tls.sh
set -u

CIPHER="GOST2012-GOST8912-GOST8912"
SPD_URL="https://fgislk.gov.ru/rmdl/"
CATALOGS="https://fgislk.gov.ru/rmdl/pvv/backend/gateway-adapter-spd/gateway/services/external/public/v1/catalogs?page=0&size=1"
FAIL=0

say() { printf '%s\n' "$*"; }
ok() { say "OK    $*"; }
bad() { say "FAIL  $*"; FAIL=1; }
info() { say "—     $*"; }

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
cd "$root"

env_get() {
  local key=$1 file=$2
  [[ -f "$file" ]] || return 0
  grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//'
}

CNF="${FGIS_OPENSSL_CONF:-}"
if [[ -z "$CNF" && -f /etc/ssl/fgislk-openssl-gost.cnf ]]; then
  CNF=/etc/ssl/fgislk-openssl-gost.cnf
fi
if [[ -z "$CNF" && -f "$here/openssl-gost.cnf" ]]; then
  CNF="$here/openssl-gost.cnf"
fi

SO="${FGIS_GOST_ENGINE:-}"
if [[ -z "$SO" ]]; then
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
fi

say "=== curl ==="
if ! command -v curl >/dev/null; then
  bad "curl не найден (sudo apt install curl)"
  exit 1
fi
curl -V | head -n 1

say ""
say "=== gost-engine ==="
if [[ -n "$SO" && -f "$SO" ]]; then
  ok "gost.so $SO"
else
  bad "gost.so нет. Один раз: sudo bash fgislk/install_gost_engine.sh"
fi
if [[ -n "$CNF" && -f "$CNF" ]]; then
  ok "OPENSSL_CONF $CNF"
else
  bad "нет openssl-gost.cnf (скрипт установки пишет /etc/ssl/fgislk-openssl-gost.cnf)"
  CNF=""
fi
if [[ -n "$CNF" ]]; then
  if OPENSSL_CONF="$CNF" openssl engine -t gost 2>/dev/null | grep -q available; then
    ok "openssl engine gost [ available ]"
  else
    bad "openssl engine gost недоступен. OPENSSL_CONF=$CNF openssl engine -t gost"
  fi
fi

say ""
say "=== СПД без GOST (ожидаем handshake failure) ==="
plain_err=$(curl -4 -sS -o /dev/null -w "http=%{http_code}" \
  --max-time 12 --tlsv1.2 --tls-max 1.2 --http1.1 \
  "$SPD_URL" 2>&1) || true
if printf '%s\n' "$plain_err" | grep -q '0A000410\|handshake failure'; then
  ok "без GOST падает как ожидалось: $plain_err"
else
  info "без GOST: $plain_err (если http=200 — GOST на этом хосте не нужен)"
fi

say ""
say "=== СПД с GOST $SPD_URL ==="
if [[ -z "$CNF" ]]; then
  bad "пропуск: нет OPENSSL_CONF"
else
  gost_out=$(OPENSSL_CONF="$CNF" curl -4 -sk -o /dev/null -w "http=%{http_code}" \
    --max-time 15 --tlsv1.2 --tls-max 1.2 --http1.1 \
    --ciphers "$CIPHER" \
    "$SPD_URL" 2>&1) || true
  if printf '%s\n' "$gost_out" | grep -q 'http=200'; then
    ok "GOST TLS к /rmdl/ $gost_out"
  else
    bad "GOST к /rmdl/ $gost_out — пока так, fgislk тоже получит 0A000410"
  fi
fi

login=$(env_get FGIS_LOGIN "$root/.env")
password=$(env_get FGIS_PASSWORD "$root/.env")
say ""
say "=== СПД catalogs (логин из .env, пароль не печатаем) ==="
if [[ -z "$CNF" ]]; then
  bad "пропуск: нет OPENSSL_CONF"
elif [[ -z "$login" || -z "$password" ]]; then
  info "в .env нет FGIS_LOGIN/FGIS_PASSWORD — только TLS без учётки"
  cat_out=$(OPENSSL_CONF="$CNF" curl -4 -sk -o /dev/null -w "http=%{http_code}" \
    --max-time 20 --tlsv1.2 --tls-max 1.2 --http1.1 \
    --ciphers "$CIPHER" \
    "$CATALOGS" 2>&1) || true
  if printf '%s\n' "$cat_out" | grep -q 'http=401'; then
    ok "TLS ок, нужна авторизация $cat_out"
  else
    info "catalogs $cat_out"
  fi
else
  cat_out=$(OPENSSL_CONF="$CNF" curl -4 -sk -o /dev/null -w "http=%{http_code}" \
    --max-time 20 --tlsv1.2 --tls-max 1.2 --http1.1 \
    --ciphers "$CIPHER" \
    -H "login: $login" \
    -H "password: $password" \
    "$CATALOGS" 2>&1) || true
  if printf '%s\n' "$cat_out" | grep -q 'http=200'; then
    ok "catalogs с учётки $cat_out"
  elif printf '%s\n' "$cat_out" | grep -q 'http=401'; then
    bad "TLS ок, учётка отклонена $cat_out"
  else
    bad "catalogs $cat_out"
  fi
fi

say ""
if [[ "$FAIL" -eq 0 ]]; then
  say "Итог: СПД с GOST доступен. Если в витрине всё ещё 0A000410 — это старый журнал; кнопки «Старт инкремента» и «Аудит» в блоке «Команды» над таблицей (колонка «Аудит» — признак, не кнопка)."
  exit 0
fi
say "Итог: TLS к СПД не готов. Сначала: sudo bash fgislk/install_gost_engine.sh"
exit 1
