#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
STATIC_DIR="$BACKEND_DIR/static"
PID_DIR="$SCRIPT_DIR/.pids"
PORT="${PORT:-8200}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

header() {
  echo ""
  echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║${NC}  ${BOLD}EasyIMM UCS Toolkit${NC}                                ${CYAN}║${NC}"
  echo -e "${CYAN}║${NC}  Cisco UCS Infrastructure Configuration Tool         ${CYAN}║${NC}"
  echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
}

check_python() {
  if command -v python3 &>/dev/null; then
    PYTHON=python3
  elif command -v python &>/dev/null; then
    PYTHON=python
  else
    echo -e "${RED}Error: Python 3 is required but not found.${NC}"
    echo "Install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
  fi

  PY_VER=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  PY_MAJOR=$($PYTHON -c 'import sys; print(sys.version_info.major)')
  PY_MINOR=$($PYTHON -c 'import sys; print(sys.version_info.minor)')

  if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo -e "${RED}Error: Python 3.10+ required (found $PY_VER).${NC}"
    exit 1
  fi
  echo -e "  ${GREEN}✓${NC} Python $PY_VER"
}

check_terraform() {
  if command -v terraform &>/dev/null; then
    TF_VER=$(terraform version -json 2>/dev/null | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['terraform_version'])" 2>/dev/null || terraform version | head -1)
    echo -e "  ${GREEN}✓${NC} Terraform $TF_VER"
  else
    echo -e "  ${YELLOW}!${NC} Terraform not found (optional -- needed for plan/apply)"
  fi
}

setup_backend() {
  echo -e "\n${BOLD}Setting up backend...${NC}"
  cd "$BACKEND_DIR"

  if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    $PYTHON -m venv venv
  fi

  source venv/bin/activate

  if [ ! -f "venv/.deps_installed" ] || [ "requirements.txt" -nt "venv/.deps_installed" ]; then
    echo "  Installing Python dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    touch venv/.deps_installed
  fi

  echo -e "  ${GREEN}✓${NC} Backend ready"
}

build_frontend() {
  if [ -f "$STATIC_DIR/index.html" ]; then
    echo -e "  ${GREEN}✓${NC} Frontend already built"
    return
  fi

  echo -e "\n${BOLD}Building frontend...${NC}"

  if ! command -v node &>/dev/null; then
    echo -e "${RED}Error: Node.js is required to build the frontend.${NC}"
    echo "Install Node.js 18+ from https://nodejs.org/"
    exit 1
  fi

  cd "$FRONTEND_DIR"

  if [ ! -d "node_modules" ]; then
    echo "  Installing npm dependencies..."
    npm ci --silent 2>/dev/null || npm install --silent
  fi

  echo "  Building production bundle..."
  npx vite build --outDir "$STATIC_DIR" --emptyOutDir
  echo -e "  ${GREEN}✓${NC} Frontend built"
}

start_server() {
  mkdir -p "$PID_DIR"
  cd "$BACKEND_DIR"
  source venv/bin/activate

  echo ""
  echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║${NC}                                                      ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}UCS Toolkit is running!${NC}                             ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                      ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  Open: ${CYAN}http://localhost:${PORT}${NC}                       ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                      ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  Press ${BOLD}Ctrl+C${NC} to stop                                ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                      ${GREEN}║${NC}"
  echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""

  exec uvicorn app:app --host 0.0.0.0 --port "$PORT"
}

stop_all() {
  echo "Stopping services..."
  for f in "$PID_DIR"/*.pid; do
    if [ -f "$f" ]; then
      pid=$(cat "$f")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        echo "  Stopped PID $pid"
      fi
      rm "$f"
    fi
  done
}

dev_mode() {
  header
  echo -e "${BOLD}Starting in development mode...${NC}"
  check_python
  check_terraform
  setup_backend

  echo -e "\n${BOLD}Starting dev servers...${NC}"
  mkdir -p "$PID_DIR"

  cd "$BACKEND_DIR"
  source venv/bin/activate
  uvicorn app:app --host 0.0.0.0 --port 8200 --reload &
  echo $! > "$PID_DIR/backend.pid"
  echo -e "  ${GREEN}✓${NC} Backend on http://localhost:8200"

  cd "$FRONTEND_DIR"
  if [ ! -d "node_modules" ]; then
    npm install --silent
  fi
  npm run dev &
  echo $! > "$PID_DIR/frontend.pid"
  echo -e "  ${GREEN}✓${NC} Frontend on http://localhost:3100"

  echo ""
  echo -e "${GREEN}Development mode running. Frontend: http://localhost:3100${NC}"
  echo "Press Ctrl+C to stop."
  wait
}

case "${1:-start}" in
  start)
    header
    echo -e "${BOLD}Checking prerequisites...${NC}"
    check_python
    check_terraform
    setup_backend
    build_frontend
    start_server
    ;;
  dev)
    dev_mode
    ;;
  build)
    header
    check_python
    setup_backend
    build_frontend
    echo -e "\n${GREEN}Build complete. Run ./run.sh to start.${NC}"
    ;;
  stop)
    stop_all
    ;;
  *)
    echo "Usage: $0 {start|dev|build|stop}"
    echo ""
    echo "  start   Build (if needed) and run the production server"
    echo "  dev     Start in development mode (hot-reload)"
    echo "  build   Build frontend without starting"
    echo "  stop    Stop background processes"
    exit 1
    ;;
esac
