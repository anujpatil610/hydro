#!/usr/bin/env sh
set -eu

REMOTE=${1:-hydropi@172.20.6.122}
REMOTE_DIR=${2:-hydro}
MODE=${3:-mock}

if [ "$MODE" != "mock" ] && [ "$MODE" != "real" ]; then
  echo "ERROR: mode must be 'mock' or 'real'"
  exit 1
fi

# Git Bash expands unquoted ~/hydro to /c/Users/... before this script runs.
case "$REMOTE_DIR" in
  /c/*|/C/*|/cygdrive/*|[A-Za-z]:*)
    echo "ERROR: REMOTE_DIR looks like a local Windows path: $REMOTE_DIR"
    echo "Git Bash expanded ~ before the script saw it. Pass a remote path instead:"
    echo "  ./deploy/install.sh $REMOTE hydro $MODE"
    exit 1
    ;;
esac

# Allow '~/hydro' only when the user quoted it (literal ~/ prefix).
case "$REMOTE_DIR" in
  "~/"*) REMOTE_DIR=${REMOTE_DIR#~/} ;;
esac

sync_repo() {
  if command -v rsync >/dev/null 2>&1; then
    rsync -az --delete \
      --exclude='.git' \
      --exclude='web/node_modules' \
      --exclude='.venv' \
      --exclude='__pycache__' \
      "./" "${REMOTE}:${REMOTE_DIR}/"
  elif command -v tar >/dev/null 2>&1; then
    # tar over ssh honors excludes (scp -r does not, and would copy .git, whose
    # read-only objects then fail to overwrite on re-deploy). No --delete, so
    # stale remote files are not removed; wipe the remote dir for a clean slate.
    echo "rsync not found; syncing via tar over ssh."
    case "$REMOTE_DIR" in
      /*) RD="$REMOTE_DIR" ;;
      *) RD="\$HOME/$REMOTE_DIR" ;;
    esac
    tar czf - \
      --exclude='.git' \
      --exclude='web/node_modules' \
      --exclude='.venv' \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='hydro.egg-info' \
      --exclude='data/*.db' \
      --exclude='data/*.db-*' \
      --exclude='.claude' \
      "./" | ssh "$REMOTE" "mkdir -p $RD && tar xzf - -C $RD"
  else
    echo "ERROR: neither rsync nor tar is available locally."
    exit 1
  fi
}

printf 'Building web assets locally...\n'
cd "$(dirname "$0")/.."
npm --prefix web run build

printf 'Syncing repository to remote: %s (%s)\n' "$REMOTE" "$REMOTE_DIR"
sync_repo

printf 'Installing and enabling service on remote\n'
ssh "$REMOTE" "REMOTE_DIR=$REMOTE_DIR MODE=$MODE bash -s" <<'REMOTE_SCRIPT'
set -eu
case "$REMOTE_DIR" in
  /*) ;;
  *) REMOTE_DIR="$HOME/$REMOTE_DIR" ;;
esac
cd "$REMOTE_DIR"
if [ ! -e .env ]; then
  cat > .env <<ENV_EOF
HYDRO_MODE=$MODE
HYDRO_HOST=0.0.0.0
HYDRO_PORT=8000
HYDRO_DB_PATH=data/hydro.db
HYDRO_POLL_SECONDS=10
HYDRO_RETENTION_HOURS=24
HYDRO_PUMP_ML_PER_MIN=50.0
HYDRO_CALIBRATION_PATH=data/calibration.json
ENV_EOF
fi
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
if [ "$MODE" = "real" ]; then
  pip install .[hardware]
else
  pip install .
fi
mkdir -p "$HOME/.config/systemd/user"
cp deploy/hydro.service "$HOME/.config/systemd/user/hydro.service"
echo "remote unit file:"
ls -l "$HOME/.config/systemd/user/hydro.service"
# Enable linger so the --user service starts at boot without an active login session.
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now hydro
systemctl --user list-unit-files | grep -E '^hydro.service\s' || true
systemctl --user status hydro --no-pager || true
REMOTE_SCRIPT
