#!/usr/bin/env bash
# Set up a family cookbook in one step: a folder with the cookbook engine, the
# browser it lays pages out with, a new book, and the AI key if you have one.
#
#   curl -fsSL https://raw.githubusercontent.com/scanady/family-cookbook/main/install.sh | bash -s -- our-cookbook
#
# Run it again in the same folder to upgrade the engine: nothing in book/ changes.
# COOKBOOK_VERSION picks another release tag; COOKBOOK_PACKAGE installs from
# somewhere else (a local clone, say).
set -euo pipefail

VERSION="${COOKBOOK_VERSION:-v1.1.0}"
PACKAGE="${COOKBOOK_PACKAGE:-family-cookbook @ git+https://github.com/scanady/family-cookbook@$VERSION}"
DIR="${1:-our-cookbook}"

say() { printf '\n==> %s\n' "$*"; }

# ask VAR "question" ["default"]: reads the terminal even when this script is piped in.
ask() {
  local answer=""
  if (exec </dev/tty) 2>/dev/null; then
    read -r -p "$2${3:+ [$3]}: " answer </dev/tty || true
  fi
  printf -v "$1" '%s' "${answer:-${3:-}}"
}

python=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    python="$candidate"
    break
  fi
done
if [ -z "$python" ]; then
  echo "The cookbook needs Python 3.11 or newer: https://www.python.org/downloads/" >&2
  exit 1
fi

mkdir -p "$DIR"
cd "$DIR"

say "Installing the cookbook engine into $PWD/.venv"
[ -d .venv ] || "$python" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet --upgrade "$PACKAGE"

say "Installing Chromium, the browser that lays out the pages (about 700 MB, once)"
.venv/bin/python -m playwright install chromium

# A launcher, so no virtual environment has to be activated: ./cookbook studio
cat >cookbook <<'EOF'
#!/bin/sh
# This book's cookbook engine, without activating .venv. Upgrade with install.sh.
exec "$(dirname "$0")/.venv/bin/cookbook" "$@"
EOF
chmod +x cookbook

if [ -f book/book.yaml ]; then
  say "Updating the guides for AI coding assistants"
  ./cookbook agent-files --update >/dev/null
else
  say "Starting the book"
  ask title "The book's title" "Our Family Cookbook"
  ask family "The line under the title, such as \"The Smith Family\" (Enter to fill it in later)"
  set -- --title "$title"
  [ -z "$family" ] || set -- "$@" --subtitle "$family"
  if ! out=$(./cookbook init "$@" 2>&1); then
    echo "$out" >&2
    exit 1
  fi
  echo "Created book/. Its chapters, their order, and colors are in book/book.yaml."
fi

if [ -z "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ] && ! grep -Eq '^GEMINI_API_KEY=.+' .env 2>/dev/null; then
  say "AI (optional): it types up photos of recipe cards and makes dish photos"
  ask key "Paste a Gemini API key from https://aistudio.google.com/apikey (Enter to skip)"
  if [ -n "$key" ]; then
    touch .env
    grep -v '^GEMINI_API_KEY=' .env >.env.new || true
    printf 'GEMINI_API_KEY=%s\n' "$key" >>.env.new
    mv .env.new .env
    chmod 600 .env
    echo "Saved to .env."
  fi
fi

say "Checking this computer"
./cookbook doctor || true

cat <<EOF

Your cookbook is in $PWD. Next:

  cd "$PWD"
  ./cookbook studio                  see the book and work on it in your browser
  ./cookbook ingest card.jpg         add a recipe from a photo of the card
  ./cookbook press                   make the two PDFs for the printer
EOF
