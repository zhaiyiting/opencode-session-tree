import html
import json

CSS = """
:root { color-scheme: light dark; }
body { font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 24px; }
h1 { font-size: 18px; margin: 0 0 4px; }
.meta { opacity: .65; margin-bottom: 16px; }
.controls { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
input[type=search] { min-width: 280px; padding: 6px 8px; }
details { margin-left: 18px; }
summary { cursor: pointer; padding: 2px 0; }
.group > summary { font-weight: 600; }
.thread { margin-left: 18px; padding: 2px 0; }
.thread-title { cursor: pointer; }
.thread-title:hover { text-decoration: underline; }
.count { opacity: .55; font-weight: 400; }
.badge { opacity: .6; font-size: 12px; margin-left: 6px; }
.detail { margin: 6px 0 12px 18px; padding: 8px 12px; border-left: 2px solid #8884; white-space: pre-wrap; }
.hidden { display: none; }
mark { background: #ffd54f; color: #000; }
"""

JS = """
const search = document.getElementById('search');
const hideSubs = document.getElementById('hide-subagents');
function apply() {
  const q = search.value.trim().toLowerCase();
  document.querySelectorAll('.thread, .group').forEach(el => {
    const text = (el.dataset.text || '').toLowerCase();
    el.classList.toggle('hidden', q !== '' && !text.includes(q));
  });
  document.querySelectorAll('.subagent').forEach(el => {
    el.classList.toggle('hidden', hideSubs.checked);
  });
}
search.addEventListener('input', apply);
hideSubs.addEventListener('change', apply);
document.getElementById('expand-all').addEventListener('click', () =>
  document.querySelectorAll('details').forEach(d => d.open = true));
document.getElementById('collapse-all').addEventListener('click', () =>
  document.querySelectorAll('details').forEach(d => d.open = false));
document.querySelectorAll('.thread-title').forEach(el => {
  el.addEventListener('click', () => {
    const detail = el.parentElement.querySelector('.detail');
    if (detail) detail.classList.toggle('hidden');
  });
});
apply();
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _thread_html(thread: dict) -> str:
    text = " ".join([
        thread.get("title", ""), thread.get("prompt", ""),
        thread.get("model") or "", thread.get("agent") or "",
    ])
    parts = [
        f'<div class="thread" data-text="{_esc(text)}">',
        f'<div class="thread-title">• {_esc(thread["title"])}'
        f'<span class="badge">{_esc(thread.get("model") or "")}</span>'
        f'<span class="badge">{thread.get("messages", 0)} msgs</span></div>',
        f'<div class="detail hidden">{_esc(thread.get("prompt") or "")}\n\n'
        f'opencode -s {_esc(thread["id"])}</div>',
        '<details><summary class="count">',
        f'{len(thread.get("forks") or [])} forks</summary>',
    ]
    parts += [
        f'<div class="fork">↳ {_esc(fork.get("title") or fork["id"])}'
        f'<span class="badge">{_esc(fork["id"])}</span></div>'
        for fork in thread.get("forks") or []
    ]
    parts.append('</details>')
    if thread.get("subagents"):
        parts.append('<details class="subagents"><summary class="count">'
                     f'{len(thread["subagents"])} subagents</summary>')
        parts += [
            f'<div class="subagent">↳ {_esc(sub.get("title") or sub["id"])}'
            f'<span class="badge">{_esc(sub["id"])}</span></div>'
            for sub in thread["subagents"]
        ]
        parts.append('</details>')
    parts.append('</div>')
    return "".join(parts)


def _node_html(node: dict) -> str:
    label = _esc(node.get("label") or "")
    count = (f'<span class="count">{node.get("threadCount", 0)} threads · '
             f'{node.get("sessionCount", 0)} sessions</span>')
    text = " ".join([node.get("label", "")] + (node.get("keywords") or []))
    body = []
    if node.get("children"):
        body += [_node_html(child) for child in node["children"]]
    for thread in node.get("threads") or []:
        body.append(_thread_html(thread))
    cls = "group" + (" general" if node.get("label") == "General / Uncategorized" else "")
    return (
        f'<details class="{cls}" data-text="{_esc(text)}" open>'
        f'<summary>{label} {count}</summary>{"".join(body)}</details>'
    )


def render_html(payload: dict) -> str:
    groups = payload.get("groups") or []
    if not groups:
        groups = [{"label": "General / Uncategorized", "keywords": [],
                   "threadCount": 0, "sessionCount": 0, "threads": []}]
    body = "".join(_node_html(node) for node in groups)
    total = sum(node.get("sessionCount", 0) for node in payload.get("groups") or [])
    threads = sum(node.get("threadCount", 0) for node in payload.get("groups") or [])
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>OpenCode Session Tree</title>
<style>{CSS}</style></head><body>
<h1>OpenCode Session Tree</h1>
<div class="meta">{threads} threads · {total} sessions · generated {_esc(payload.get("generatedAt", ""))}</div>
<div class="controls">
<input id="search" type="search" placeholder="Search titles, prompts, groups...">
<label><input id="hide-subagents" type="checkbox" checked> hide subagents</label>
<button id="expand-all">expand all</button>
<button id="collapse-all">collapse all</button>
</div>
<div id="tree">{body}</div>
<script>{JS}</script>
</body></html>"""
