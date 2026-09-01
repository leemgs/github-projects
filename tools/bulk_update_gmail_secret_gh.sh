#!/usr/bin/env bash
#
# Alternative implementation using the GitHub CLI (`gh`), which handles the
# sealed-box encryption for you. Use this if you already have `gh` installed
# and authenticated (`gh auth login`) and don't want to install PyNaCl.
#
# By default it updates ONLY repos that already have the secret. Every repo is
# read from ../docs/projects.json (derived from each entry's html_url).
#
# Usage:
#   export GMAIL_APP_PASSWORD_NEW='new-app-password'
#   ./bulk_update_gmail_secret_gh.sh                 # update existing only
#   ./bulk_update_gmail_secret_gh.sh --create-missing
#   ./bulk_update_gmail_secret_gh.sh --dry-run
#   SECRET_NAME=GMAIL_APP_PASSWORD ./bulk_update_gmail_secret_gh.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECTS_JSON="${PROJECTS_JSON:-$SCRIPT_DIR/../docs/projects.json}"
SECRET_NAME="${SECRET_NAME:-GMAIL_APP_PASSWORD}"

CREATE_MISSING=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --create-missing) CREATE_MISSING=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

command -v gh >/dev/null 2>&1 || { echo "ERROR: gh CLI not found." >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq not found." >&2; exit 2; }

VALUE="${GMAIL_APP_PASSWORD_NEW:-}"
if [[ $DRY_RUN -eq 0 && -z "$VALUE" ]]; then
  read -r -s -p "New secret value (hidden): " VALUE; echo
  [[ -n "$VALUE" ]] || { echo "ERROR: empty value." >&2; exit 2; }
fi

mapfile -t REPOS < <(jq -r '.[].html_url | sub("/$";"") | split("/") | .[-2] + "/" + .[-1]' "$PROJECTS_JSON")

echo "Secret : $SECRET_NAME"
echo "Repos  : ${#REPOS[@]}"
echo "Mode   : $([[ $DRY_RUN -eq 1 ]] && echo DRY-RUN || echo LIVE)"
echo

updated=0; skipped=0; failed=0
for repo in "${REPOS[@]}"; do
  if gh secret list --repo "$repo" 2>/dev/null | awk '{print $1}' | grep -qx "$SECRET_NAME"; then
    exists=1
  else
    exists=0
  fi

  if [[ $exists -eq 0 && $CREATE_MISSING -eq 0 ]]; then
    echo "  -  $repo: not present -> skip"; skipped=$((skipped+1)); continue
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  ~  $repo: would set $SECRET_NAME"; updated=$((updated+1)); continue
  fi

  if gh secret set "$SECRET_NAME" --repo "$repo" --body "$VALUE" >/dev/null 2>&1; then
    echo "  *  $repo: set $SECRET_NAME"; updated=$((updated+1))
  else
    echo "  !  $repo: FAILED"; failed=$((failed+1))
  fi
done

echo
echo "--- Summary --- set/would-set: $updated  skipped: $skipped  failed: $failed"
[[ $failed -eq 0 ]]
