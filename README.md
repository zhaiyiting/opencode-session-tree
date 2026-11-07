# OpenCode Session Tree

Turn a messy OpenCode session history into a small set of topic groups you can browse as a collapsible tree.

OpenCode groups sessions by working directory and gives them auto-generated titles. That stops working once you have hundreds of sessions, 100+ subagent runs, and fork families from the same root conversation. This tool ignores directories entirely. It reads the conversation text, clusters threads by topic, and writes one self-contained HTML page.

- **No LLM.** TF-IDF and k-means, standard library only.
- **No network.** Nothing leaves your machine.
- **Read-only.** The OpenCode database is opened with `mode=ro` and never modified.
- **Offline output.** A single HTML file with no CDN, fonts, or external assets.

## What it looks like

```text
▾ memory allocators
  ▾ mimalloc
    • mi_collect API in mimalloc v3
      ├─ fork #1
      ├─ fork #2
      └─ subagents (12)
  ▸ jemalloc
  ▸ tcmalloc
▾ OpenCode internals
  ▾ session and storage
  ▾ tools and agents
▾ MCP and agent frameworks
▸ install / setup / environment
▸ General / Uncategorized
```

Groups expand and collapse, the search box filters titles and prompts, and each thread has a detail panel with its first prompt, date, model, agent, message count, and a copyable `opencode -s <id>` resume command.

## Quick start

Requirements: Python 3.9+ with `sqlite3` (the system Python is fine), and an OpenCode v2 SQLite database at the default location:

```text
~/.local/share/opencode/opencode.db
```

Run:

```bash
git clone https://github.com/zhaiyiting/opencode-session-tree.git
cd opencode-session-tree
python3 session_tree.py --out out
open out/session-tree.html        # macOS
# xdg-open out/session-tree.html  # Linux
```

No dependencies to install.

## Usage

```bash
python3 session_tree.py [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--db PATH` | `~/.local/share/opencode/opencode.db` | OpenCode SQLite database |
| `--out DIR` | `out` | Directory for `session-tree.html` and `groups.json` |
| `--groups N` | `10` | Number of top-level topic groups |
| `--subgroups N` | `3` | Maximum children when a large group splits |

Examples:

```bash
# More top-level topics
python3 session_tree.py --groups 14

# Use a copied database and a different output directory
python3 session_tree.py --db ~/backup/opencode.db --out ~/Desktop/session-tree
```

Re-run the command after new sessions appear, then refresh the page.

## How it works

1. **Read text parts only.** The `message` table holds metadata; the conversation text lives in `part` rows with `type = 'text'`. Tool calls, patches, files, and reasoning are ignored.
2. **Reconstruct threads.**
   - Forks are detected by an identical first user prompt plus an identical first `message.time_created`. Forked sessions do not share message IDs or a parent link, so content and timestamp are the reliable signal.
   - Subagent sessions are attached to their parent via `session.parent_id`.
   - Clustering runs on one thread per fork family; forks and subagents inherit the thread's group.
3. **Build message-level TF-IDF vectors.** User messages weigh more than assistant messages. Terms appearing in more than 35% of messages are dropped as boilerplate. Duplicate messages copied into forks are counted once.
4. **Cluster with spherical k-means.** Deterministic multi-restart k-means splits threads into top-level groups, then recursively into at most `--subgroups` children, to a maximum depth of three.
5. **Label mechanically.** Each node gets its top three weighted terms; a group with no useful terms falls back to a representative thread title.
6. **Render one HTML file.** Counts, search, filters, fork branches, and subagent nesting are all embedded in the page.

Sessions with under 20 characters of user text go to **General / Uncategorized** rather than influencing the topic structure.

## Output

| File | Contents |
|---|---|
| `out/session-tree.html` | Self-contained page; open it directly from disk |
| `out/groups.json` | The same tree as structured data, for scripting or a future TUI |

`threadCount` counts unique conversations (fork families). `sessionCount` counts every session in the subtree, including forks and subagents.

## Privacy

The generated HTML contains your prompts and session titles, including anything you pasted into OpenCode. Treat `out/` as private. Keep it out of version control; the included `.gitignore` already ignores it.

The tool itself makes no network requests and does not write to the OpenCode database.

## Limitations

- **Message text only.** Two sessions about "exploring this project" but different projects can land together. Directories are deliberately ignored, so this is expected.
- **Generic prompts cluster.** Phrasing such as "review the code" or "create AGENTS.md" is a strong signal even across unrelated work.
- **Labels are hints, not titles.** They are built from weighted terms and can read oddly, especially with mixed Chinese/English prompts. `--groups` is the main knob.
- **No live updates.** Regenerate after new sessions.
- **Fork detection is heuristic.** It relies on timestamps being preserved when a session is forked. If OpenCode changes that behavior, families may split; the generator still emits every session exactly once.
- **Not affiliated with OpenCode.** This is a local analysis tool that reads OpenCode's data format.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Layout:

```text
session_tree.py          CLI entry point
sessiontree/
  load.py                read-only SQLite access
  lineage.py             fork families and subagent attachment
  features.py            tokenization, TF-IDF, thread vectors
  cluster.py             k-means and recursive tree building
  labels.py              node labels from weighted terms
  export.py              JSON payload and counts
  render.py              self-contained HTML
  validate.py            invariant checks
tests/                   unit, integration, and generated-JS search tests
```

The test suite uses both a small synthetic database and a Node-driven fake DOM to verify the generated search code. It does not read your real session database.

Design and implementation notes live in [`docs/superpowers/`](docs/superpowers/).
