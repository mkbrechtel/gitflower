"""`python3 -m gitflower` — same entry point as the console script.

The hook shim falls back to this form (via GITFLOWER_BIN) in test
environments where the console script is not installed.
"""

from gitflower.cli import main

main()
