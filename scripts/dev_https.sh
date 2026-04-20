#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CERT_DIR="$ROOT_DIR/.certs"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/dev_https.pid"
LOG_FILE="$LOG_DIR/dev_https.log"

ROOT_CA_KEY="$CERT_DIR/dev-root-ca-key.pem"
ROOT_CA_CERT="$CERT_DIR/dev-root-ca-cert.pem"
ROOT_CA_CFG="$CERT_DIR/dev-root-ca.cnf"

LEAF_KEY="$CERT_DIR/localhost-leaf-key.pem"
LEAF_CSR="$CERT_DIR/localhost-leaf.csr"
LEAF_CERT="$CERT_DIR/localhost-leaf-cert.pem"
LEAF_CFG="$CERT_DIR/localhost-leaf.cnf"

HOST="127.0.0.1"
PORT="8000"
MODE="foreground"

usage() {
  cat <<'EOF'
Usage:
  scripts/dev_https.sh up [--background] [--host 127.0.0.1] [--port 8000]
  scripts/dev_https.sh down

Examples:
  scripts/dev_https.sh up
  scripts/dev_https.sh up --background
  scripts/dev_https.sh down
EOF
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_tools() {
  if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "Missing Python virtualenv at .venv/bin/python"
    exit 1
  fi
  if ! command_exists openssl; then
    echo "openssl is required"
    exit 1
  fi
  if ! command_exists security; then
    echo "macOS security tool is required"
    exit 1
  fi
}

stop_existing() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")" || true
    rm -f "$PID_FILE"
  fi

  local pids
  pids="$(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    for p in $pids; do
      kill "$p" || true
    done
  fi
}

generate_root_ca_if_needed() {
  mkdir -p "$CERT_DIR"

  if [[ -f "$ROOT_CA_KEY" && -f "$ROOT_CA_CERT" ]]; then
    return
  fi

  cat > "$ROOT_CA_CFG" <<'EOF'
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_ca

[dn]
C = NL
ST = Noord-Holland
L = Amsterdam
O = Careon Local Dev
CN = Careon Local Root CA

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, keyCertSign, cRLSign
EOF

  openssl req -x509 -new -nodes -days 3650 \
    -keyout "$ROOT_CA_KEY" \
    -out "$ROOT_CA_CERT" \
    -config "$ROOT_CA_CFG"
}

generate_leaf_cert() {
  cat > "$LEAF_CFG" <<'EOF'
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = req_ext

[dn]
C = NL
ST = Noord-Holland
L = Amsterdam
O = Careon Local Dev
CN = localhost

[req_ext]
subjectAltName = @alt_names
basicConstraints = critical, CA:false
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

  openssl req -new -nodes \
    -keyout "$LEAF_KEY" \
    -out "$LEAF_CSR" \
    -config "$LEAF_CFG"

  openssl x509 -req \
    -in "$LEAF_CSR" \
    -CA "$ROOT_CA_CERT" \
    -CAkey "$ROOT_CA_KEY" \
    -CAcreateserial \
    -out "$LEAF_CERT" \
    -days 825 \
    -sha256 \
    -extfile "$LEAF_CFG" \
    -extensions req_ext
}

trust_root_ca() {
  security delete-certificate -c localhost "$HOME/Library/Keychains/login.keychain-db" >/dev/null 2>&1 || true

  local sha
  sha="$(openssl x509 -in "$ROOT_CA_CERT" -noout -fingerprint -sha256 | cut -d'=' -f2 | tr -d ':')"

  if ! security find-certificate -a -Z "$HOME/Library/Keychains/login.keychain-db" | grep -q "$sha"; then
    security add-trusted-cert -d -r trustRoot \
      -k "$HOME/Library/Keychains/login.keychain-db" \
      "$ROOT_CA_CERT"
  fi
}

start_server() {
  mkdir -p "$LOG_DIR"
  local cmd=(
    "$ROOT_DIR/.venv/bin/python" -m uvicorn config.asgi:application
    --host "$HOST"
    --port "$PORT"
    --ssl-keyfile "$LEAF_KEY"
    --ssl-certfile "$LEAF_CERT"
  )

  if [[ "$MODE" == "background" ]]; then
    : > "$LOG_FILE"
    nohup "${cmd[@]}" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    local tries=0
    while [[ $tries -lt 20 ]]; do
      if lsof -i "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        break
      fi
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "HTTPS dev server failed to start. See $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
      fi
      sleep 0.2
      tries=$((tries + 1))
    done

    if ! lsof -i "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "HTTPS dev server did not open port $PORT in time. See $LOG_FILE"
      rm -f "$PID_FILE"
      return 1
    fi

    echo "HTTPS dev server started in background (pid $pid)."
    echo "URL: https://$HOST:$PORT/"
    echo "Log: $LOG_FILE"
  else
    echo "Starting HTTPS dev server on https://$HOST:$PORT/"
    exec "${cmd[@]}"
  fi
}

ACTION="${1:-up}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --background)
      MODE="background"
      shift
      ;;
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

case "$ACTION" in
  up)
    require_tools
    stop_existing
    generate_root_ca_if_needed
    generate_leaf_cert
    trust_root_ca
    start_server
    ;;
  down)
    stop_existing
    echo "HTTPS dev server stopped (if it was running)."
    ;;
  *)
    echo "Unknown action: $ACTION"
    usage
    exit 1
    ;;
esac
