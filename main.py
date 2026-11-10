"""Kept for backwards compatibility: `python main.py` starts Awlchemy.

    python main.py              start the app (opens your browser)
    python main.py sync         download new patterns from Drive, then index
    python main.py --help       all commands
"""

from awlchemy.cli import main

if __name__ == "__main__":
    main()
