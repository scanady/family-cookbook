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

VERSION="${COOKBOOK_VERSION:-v1.2.1}"
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

if [ -z "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}${OPENROUTER_API_KEY:-}" ] &&
   ! grep -Eq '^(GEMINI|OPENROUTER)_API_KEY=.+' .env 2>/dev/null; then
  say "AI (optional): it types up photos of recipe cards and makes dish photos"
  echo "  1) OpenRouter (recommended): prepaid credits, no Google billing to set up"
  echo "  2) Google AI Studio: a Gemini API key"
  echo "  3) Skip: no AI for now; add a key to .env later"
  while :; do
    ask choice "Which one" "1"
    case "$choice" in
      1) var=OPENROUTER_API_KEY url=https://openrouter.ai/keys prefix=sk-or- ;;
      2) var=GEMINI_API_KEY url=https://aistudio.google.com/apikey prefix= ;;
      3) var= ;;
      *) echo "Type 1, 2, or 3."; continue ;;
    esac
    break
  done
  if [ -n "$var" ]; then
    ask key "Paste your key from $url (Enter to skip)"
    if [ -n "$key" ]; then
      if [ -n "$prefix" ] && [ "${key#"$prefix"}" = "$key" ]; then
        echo "That does not look like an OpenRouter key (they start $prefix); saving it anyway."
      fi
      touch .env
      grep -v "^$var=" .env >.env.new || true
      printf '%s=%s\n' "$var" "$key" >>.env.new
      mv .env.new .env
      chmod 600 .env
      echo "Saved to .env as $var."
    fi
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
