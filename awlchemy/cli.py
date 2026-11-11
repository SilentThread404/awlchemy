"""Command line entry point.

    awlchemy                 start the app and open it in your browser
    awlchemy serve --port 8765 --no-browser
    awlchemy source add NAME <drive-folder-link | folder-path>
    awlchemy source list | remove NAME
    awlchemy sync [--dry-run] [--source NAME]   fetch new patterns from your sources, then index
    awlchemy index              re-scan library/ (after copying PDFs in by hand)
    awlchemy import <link-or-file> [--collection NAME]
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from . import config, db, importer, indexer, sources


def cmd_serve(args) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    print(f"Awlchemy is running at {url}  (close this window to stop it)")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("awlchemy.app:app", host="127.0.0.1", port=args.port, log_level="warning")


def cmd_sync(args) -> None:
    db.init()
    try:
        result = sources.sync_all(dry_run=args.dry_run, only=args.source)
    except ValueError as ex:
        sys.exit(str(ex))
    if not args.dry_run:
        indexer.scan()
        config.save_settings({"last_sync": db.now()})
    sys.exit(1 if result.failed else 0)


def cmd_source_add(args) -> None:
    try:
        s = sources.add_source(args.name, args.location)
    except ValueError as ex:
        sys.exit(str(ex))
    print(f"Added '{s['name']}' ({s['kind']}). Run `awlchemy sync` to fetch it.")


def cmd_source_list(_args) -> None:
    items = sources.list_sources()
    if not items:
        print("No sources yet. Add one with: awlchemy source add <name> <drive-link-or-folder>")
    for s in items:
        print(f"{s['name']:<24} {s['kind']:<7} {s['location']}" + ("" if s.get("enabled", True) else "  (disabled)"))


def cmd_source_remove(args) -> None:
    stored = next((s["name"] for s in sources.list_sources() if s["name"].lower() == args.name.lower()), args.name)
    try:
        sources.remove_source(args.name, delete_files=args.delete_files)
    except (ValueError, OSError) as ex:
        sys.exit(str(ex))
    if args.delete_files:
        db.init()
        r = indexer.purge_source(stored)
        print(f"Removed '{args.name}' and {r['removed']} pattern file(s) from the library."
              + (f" {r['kept']} with your notes or guides stay in the database." if r["kept"] else ""))
    else:
        print(f"Removed '{args.name}'. Its files stay in library/{args.name}/ "
              "(use --delete-files to remove them too).")


def cmd_index(_args) -> None:
    indexer.scan()


def cmd_import(args) -> None:
    db.init()
    src = args.source
    if Path(src).exists():
        p = Path(src)
        with open(p, "rb") as fh:
            dest = importer.import_upload(p.name, fh, args.collection)
        print(f"  + {dest}")
    else:
        importer.import_url(src, args.collection)
    indexer.scan()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="awlchemy", description="Your leathercraft pattern library and teacher.")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="start the web app")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("sync", help="fetch new files from your pattern sources")
    s.add_argument("--dry-run", action="store_true", help="only list what would be downloaded")
    s.add_argument("--source", help="only this source (by name)")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("source", help="manage where your patterns come from")
    ss = s.add_subparsers(dest="action", required=True)
    a = ss.add_parser("add", help="add a shared Google Drive folder link or a local folder")
    a.add_argument("name", help="a short name; also the folder name under library/")
    a.add_argument("location", help="Drive folder link, or a folder path on this computer")
    a.set_defaults(func=cmd_source_add)
    a = ss.add_parser("list", help="show your sources")
    a.set_defaults(func=cmd_source_list)
    a = ss.add_parser("remove", help="forget a source (downloaded files are kept)")
    a.add_argument("name")
    a.add_argument("--delete-files", action="store_true", help="also delete its patterns from the library")
    a.set_defaults(func=cmd_source_remove)

    s = sub.add_parser("index", help="re-scan the library folder")
    s.set_defaults(func=cmd_index)

    s = sub.add_parser("import", help="add a pattern from a link or a local file")
    s.add_argument("source")
    s.add_argument("--collection")
    s.set_defaults(func=cmd_import)

    args = ap.parse_args(argv)
    if not args.cmd:
        args = ap.parse_args(["serve", *(argv or sys.argv[1:])])
    config.ensure_dirs()
    args.func(args)


if __name__ == "__main__":
    main()
