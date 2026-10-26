#!/usr/bin/env bash
# Keeps data/datapulse.db alive between ephemeral CI runs by storing it on an orphan branch
# named "state". Usage: sync_state.sh pull|push
# Requires GITHUB_TOKEN and GITHUB_REPOSITORY in the environment (set by the workflow).
set -euo pipefail

ACTION="${1:?usage: sync_state.sh pull|push}"
BRANCH="state"
DB="data/datapulse.db"
REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
WORK="$(mktemp -d)"

clone_state() {
  # stderr is discarded so a failed clone can never echo the tokenised URL
  git clone --quiet --depth 1 --branch "$BRANCH" "$REMOTE" "$WORK" 2>/dev/null
}

case "$ACTION" in
  pull)
    mkdir -p data
    if clone_state; then
      cp "$WORK/datapulse.db" "$DB"
      echo "Restored state from branch '$BRANCH'"
    else
      echo "No prior state found; starting with an empty database"
    fi
    ;;
  push)
    if [ ! -f "$DB" ]; then
      echo "No database to save"
      exit 0
    fi
    if ! clone_state; then
      git init --quiet -b "$BRANCH" "$WORK"
      git -C "$WORK" remote add origin "$REMOTE"
    fi
    cp "$DB" "$WORK/datapulse.db"
    cd "$WORK"
    git config user.name "datapulse-bot"
    git config user.email "datapulse-bot@users.noreply.github.com"
    git add datapulse.db
    if git diff --cached --quiet; then
      echo "State unchanged"
      exit 0
    fi
    git commit --quiet -m "Update state $(date -u +%F)"
    git push --quiet origin "$BRANCH" 2>/dev/null
    echo "Saved state to branch '$BRANCH'"
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 2
    ;;
esac
