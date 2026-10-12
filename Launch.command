#!/bin/zsh
# Launch the Internship Planner on macOS (double-click in Finder).
# First run creates a virtual environment and installs requirements.

cd "$(dirname "$0")" || exit 1

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv || { echo "Python 3 is required."; read -k 1; exit 1; }
  .venv/bin/pip install --quiet --upgrade pip
fi

# Reinstall only when requirements.txt has changed.
if [ ! -f ".venv/.installed" ] || [ requirements.txt -nt .venv/.installed ]; then
  echo "Installing requirements..."
  .venv/bin/pip install --quiet -r requirements.txt && touch .venv/.installed
fi

echo "Starting Internship Planner. Press Ctrl+C to stop."
PYTHONPATH=src .venv/bin/python -m internship_planner.app "$@"

echo
echo "The app has stopped. Press any key to close this window."
read -k 1
