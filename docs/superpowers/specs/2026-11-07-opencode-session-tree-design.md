# OpenCode Session Tree — Design

Date: 2026-11-07
Status: draft for approval

## Intent

Turn the local OpenCode session history into a small number of topic groups
that can be explored as a collapsible tree in a browser. Grouping must use
conversation content only, never repository/directory boundaries, and must not
call an LLM. Forks and subagent sessions must be folded into the lineage they
belong to instead of appearing as separate topics.

The user's complaint: auto-generated session titles make the flat session list
hard to navigate, and the existing "project" grouping is just the working
directory. They do not care about project folders.

## What exists today (measured on the user's DB)

- `~/.local/share/opencode/opencode.db` (SQLite, ~1.4 GB).
- 316 sessions: 174 roots, 142 subagent children, 14 fork families covering
  32 root sessions.
- Text lives in `part` rows, not `message` rows:
  - 1,047 user `text` parts (~813k chars)
  - 1,943 assistant `text` parts (~1.35M chars)
  - plus `reasoning`, `tool`, `patch`, `file` parts that this tool ignores.
- Forks are not linked by `parent_id` and carry no fork metadata. They are
  detectable by an identical first user text plus an identical
  `message.time_created` (the part timestamps are regenerated on fork; message
  timestamps are preserved).
- Subagents are linked by `session.parent_id`.
- 128 sessions have `project_id = 'global'` because their directories are not
  git repositories, so project/directory is not a usable grouping axis.

Recon scripts showed message-only TF-IDF + clustering produces recognizable
groups (memory allocators, OpenCode internals, MCP/agent-browser, setup tasks,
the text-capture app), while naive whole-session TF-IDF collapses into one
large blob. The design below uses message-level vectors and keeps an explicit
General bucket.

## Goals

- One self-contained HTML file that opens offline and shows all sessions in a
  collapsible topic tree.
- Topic groups derived only from user + assistant message text.
- Forks and subagents nested under their lineage, never counted as separate
  top-level work.
- Search and filtering in the page.
- Fast: analysis and generation under ~10 seconds for the current DB.
- Reproducible: rerunning produces the same structure for the same input.

## Non-goals

- No LLM calls, embeddings, or network requests of any kind.
- No writes to the OpenCode DB; no session renaming, deleting, or moving.
- No grouping by project, repository, or directory.
- No live watcher or server. Regenerate on demand.
- No attempt to replace OpenCode's own session UI.

## Anti-goals (would make this a failure)

- A fork family split across groups.
- 142 subagent sessions dominating the tree.
- One giant catch-all group containing most of the history.
- An HTML file that depends on a CDN or cannot be opened by double-click.

## Approaches considered

1. **Static HTML from a stdlib-only Python script (chosen).** Lowest
   operational cost, easiest to inspect and share, fast iteration on grouping
   quality. Clustering output is also written as JSON so a TUI can reuse it.
2. **Terminal TUI.** Better in-workflow resuming, but 3–4× the code and slower
   to judge whether groups are good. Deferred.
3. **Local web server.** Richer interactions, unnecessary for ~300 sessions.
4. **Embedding model + HDBSCAN.** Likely better semantic clusters, but adds a
   model dependency, which conflicts with the "no LLM" constraint and adds
   install weight. Rejected for v1.

## Decisions

- Language/runtime: Python 3, standard library only. Use `/usr/bin/python3`;
  the Anaconda Python on this machine has a broken `sqlite3` extension.
- Location: `/Users/zhai/wsp/opencode_session_tree/`.
- DB access: SQLite URI `file:...?mode=ro`, read-only. Never open the live DB
  for writing while OpenCode is running.
- Output: `out/session-tree.html` (self-contained) and `out/groups.json`
  (intermediate data).
- CLI:
  `python3 session_tree.py [--db PATH] [--out DIR] [--groups N] [--subgroups N]`
  with defaults `~/.local/share/opencode/opencode.db`, `out/`, 10, 3.

## Analysis pipeline

### 1. Load and normalize

- Read `session` (id, parent_id, title, directory, time_created,
  time_updated, agent, model).
- Read `part` joined to `message` where part type is `text`; collect per
  session, ordered by `message.time_created` then `part.time_created`:
  - `user_text`: concatenated user text parts
  - `assistant_text`: concatenated assistant text parts
- Ignore `reasoning`, `tool`, `patch`, `file`, `step-*`, `subtask`,
  `compaction`, `agent` parts.

### 2. Reconstruct lineage

- **Fork family key**: `(normalized first user text, min(message.time_created))`.
  Normalize by stripping whitespace and collapsing runs of spaces.
  Sessions sharing a key form one family.
- **Root family**: the earliest session in the family (by `time_created`).
  Other members are forks.
- **Subagent**: `parent_id` not null. Attach to the parent's family; if the
  parent is itself a fork, attach to the family root.
- **Orphans**: a fork family with no surviving root, or a subagent whose parent
  is missing, becomes its own thread.
- **Cluster unit**: one root-family per unique conversation thread. Forks and
  subagents do not participate in clustering; they inherit the family's group.

### 3. Text features (messages only)

- Tokenization:
  - lowercase ASCII words of length ≥ 3, keeping `_ . / : + -` inside tokens;
    drop tokens starting with `http`
  - Chinese: CJK character bigrams
  - drop a small English stopword list
- Build **message-level** TF-IDF over all user + assistant text parts.
- Drop terms whose document frequency exceeds 35% of messages (boilerplate
  such as "let me", "this project", assistant filler).
- **Family vector**: the clustering vector for a thread is built from the root
  session **and its forks**, because a fork often contains more conversation
  than the root. Subagent text is excluded: subagents are batch/exploration
  tasks and would pull a family toward their own wording.
- Within the vector, user messages weight 2, assistant messages weight 1. This
  prevents long assistant answers from dominating short, intent-carrying
  prompts.
- A thread whose root **user text** is under 20 characters goes directly to
  **General / Uncategorized** and is excluded from clustering. (User text, not
  total text: assistant-only sessions have low intent signal.)

### 4. Clustering into a tree

- Distance: `1 - cosine(family_vector_i, family_vector_j)`.
- Agglomerative average-linkage clustering over root families.
- The tree is **recursive**, not fixed at two levels. A node holds either
  `children` (further split) or `threads` (leaves), never both. Maximum depth is
  3 (top group → subgroup → sub-subgroup); the renderer is recursive and does
  not assume a fixed depth.
- Cut the dendrogram once for top-level groups (`--groups`, default 10).
- Recursively split any node with more than 6 **threads** until it has at most
  `--subgroups` (default 3) children, or the depth limit is reached.
- If a node ends up with a single child, replace the node with that child.
- Nodes with fewer than 2 threads merge into the nearest larger sibling unless
  they are the only member of their branch; truly isolated threads may remain
  as one-thread leaves under General.
- **Thresholds (split at >6, merge at <2) count threads only**, because forks
  and subagents are not independent evidence.
- **Displayed counts count every session in the subtree**, including forks and
  subagents, so the user sees the true volume. Each node exposes
  `threadCount` and `sessionCount`; the UI shows both, e.g. `9 threads · 23
  sessions`. The 40% validation check uses `threadCount`, not `sessionCount`.

### 5. Labels

- Node label = top 3 weighted terms from the node's own cluster, after removing
  terms already in the parent label.
- If no useful terms remain, use the title of the highest-weight session in the
  node.
- Node subtitle = session count.
- Labels are intentionally mechanical; the tool is for exploration, not
  publication.

### 6. Tree data model

The renderer is recursive. A node has either `children` or `threads`, never
both.

```json
{
  "generatedAt": "2026-11-07T...",
  "groups": [
    {
      "label": "memory allocators",
      "keywords": ["mimalloc", "jemalloc", "arena"],
      "threadCount": 9,
      "sessionCount": 23,
      "children": [
        {
          "label": "mimalloc",
          "threadCount": 4,
          "sessionCount": 11,
          "threads": [
            {
              "id": "ses_...",
              "title": "mi_collect API in mimalloc v3",
              "prompt": "this is the mimalloc v3 version...",
              "updated": 1775722883592,
              "messages": 116,
              "model": "MiniMax-M2.1",
              "agent": "build",
              "forks": [{"id": "ses_...", "title": "... (fork #1)"}],
              "subagents": [
                {"id": "ses_...", "title": "... (@explore subagent)", "agent": "explore"}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

- `threadCount` counts unique conversation threads (fork families).
  `sessionCount` counts every session in the subtree.
- `model` and `agent` prefer the latest assistant `message.data` values
  (`modelID`, `providerID`, `agent`), then fall back to the `session` columns.
  Message data is present for 308 of 316 sessions; session columns only for 56.
- Every session in the DB appears exactly once in the JSON, either as a thread
  root, a fork, or a subagent.
- Empty or near-empty sessions appear under `General / Uncategorized`.

## HTML page

- One file, embedded JSON, no external assets or CDN.
- `<details>/<summary>` for native collapse, with small JS only for search,
  counts, and "expand/collapse all".
- Header: total sessions, generated timestamp, search box.
- Tree rows:
  - group: label + count
  - subgroup: label + count
  - thread: title, relative date, message count; clicking expands detail
  - fork: fork label, indented under thread
  - subagent: title + agent name, indented under thread
- Detail panel on thread click: full first user prompt, title, timestamps,
  model, agent, and a copyable `opencode -s <id>` resume command.
- Filters:
  - text search over title, prompt, group label, and keywords
  - checkbox: hide/show subagents (default: hidden, shown as a count)
  - checkbox: hide/show forks (default: shown)
- A visible "General / Uncategorized" branch, always last.
- Works with `file://`; no fetch calls.
- Styling: system font stack, light/dark via `prefers-color-scheme`, no
  external fonts or icons.

## Validation

Automated checks in the generator:

1. Every DB session appears exactly once across the output.
2. All members of a fork family resolve to the same thread.
3. Every subagent's thread is its parent's thread.
4. No group is empty; no group contains > 40% of threads unless the DB
   genuinely has one dominant topic (warn, do not fail). Counts use
   `threadCount`, not `sessionCount`.
5. JSON schema is stable and the HTML contains no `http://` or `https://`
   asset references.

Manual check after generation:

- Open the file offline, expand 10 random groups, and judge whether membership
  is plausible.
- Verify search finds a known session by a phrase from its first prompt.
- Verify a fork family (e.g. openTPU) renders under one thread.

## What is left to the builder

- Exact stopword list and token regex details.
- Linkage-cut heuristics and merge thresholds.
- Visual layout and CSS.
- Whether to add a "copy group as Markdown" convenience later.
- Whether to expose `--min-messages` or other tuning flags.

## Risks

- Message-only clustering cannot reliably distinguish sessions that are about
  "exploring a project" but different projects. They will share the General or
  exploration branch. This is accepted; directory grouping is explicitly out
  of scope.
- 13 root sessions have almost no user text. They will be uncategorized.
- Fork detection relies on preserved message timestamps and first-prompt text.
  If OpenCode changes fork behavior, detection degrades to title-based
  heuristics; the generator should report how many families it found so this
  is visible.
