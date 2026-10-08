#!/bin/zsh
cd "${0:A:h}"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python app.py
elif [[ -x "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python" ]]; then
  "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python" app.py
else
  python3 app.py
fi
