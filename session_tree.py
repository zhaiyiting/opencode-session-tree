import argparse
import json
import os
import sys
from datetime import datetime, timezone

from sessiontree.cluster import build_tree
from sessiontree.export import to_payload
from sessiontree.features import build_vectors
from sessiontree.labels import assign_labels
from sessiontree.lineage import build_threads
from sessiontree.load import load_raw
from sessiontree.render import render_html
from sessiontree.validate import validate_payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Group OpenCode sessions into a browsable tree.")
    parser.add_argument("--db", default=os.path.expanduser("~/.local/share/opencode/opencode.db"))
    parser.add_argument("--out", default="out")
    parser.add_argument("--groups", type=int, default=10)
    parser.add_argument("--subgroups", type=int, default=3)
    args = parser.parse_args(argv)

    raw = load_raw(args.db)
    threads = build_threads(raw)
    vectors, general = build_vectors(threads)
    nodes = build_tree(list(vectors), vectors, general, groups=args.groups, subgroups=args.subgroups)
    by_id = {thread.root_id: thread for thread in threads}
    assign_labels(nodes, vectors, by_id)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = to_payload(nodes, by_id, generated)

    errors = validate_payload(payload, raw)
    if errors:
        for error in errors:
            print(f"warning: {error}", file=sys.stderr)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "groups.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "session-tree.html"), "w", encoding="utf-8") as fh:
        fh.write(render_html(payload))

    print(f"{len(threads)} threads, {len(raw.sessions)} sessions")
    print(f"wrote {os.path.join(args.out, 'session-tree.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
