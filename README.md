# mindloom

Weave raw knowledge into structured Obsidian wikis, powered by Claude Code.

Inspired by [Andrej Karpathy's LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595) workflow.
You curate (paste a link). Claude Code thinks (compile, cross-link, answer, lint).

## Install

```bash
# Recommended: global install via uv (works from anywhere)
uv tool install mindloom

# Optional: browser extra for JS-heavy sites
uv tool install "mindloom[browser]"
```

**Requires:** Python 3.12+, [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed for compile / ask / lint.

## How it works

```
loom add <url> -v ~/my-wiki
  ├─ 1. fetch: trafilatura / playwright / pymupdf (PDF)   (Python)
  ├─ 2. images downloaded, paths rewritten                 (Python)
  ├─ 3. saved to raw/ with YAML frontmatter                (Python)
  └─ 4. claude -p "compile this into the wiki"             (Claude Code)
         ├─ reads CLAUDE.md (the rules)
         ├─ reads _index.md (what exists)
         ├─ uses loom search + Grep to find related articles
         ├─ writes/updates wiki/ articles with [[wikilinks]]
         └─ updates _index.md
```

## Usage

Every command (except `init`) requires `--vault` / `-v` pointing to your vault.

```bash
# Create a vault (open it in Obsidian)
loom init ~/my-wiki

# Add articles — fetches + auto-compiles
loom add "https://arxiv.org/abs/..." -t "transformers, attention" -v ~/my-wiki
loom add "https://blog.example.com" -t "rl, rlhf" -v ~/my-wiki
loom add "https://..." --no-compile -v ~/my-wiki   # just fetch, compile later

# Compile pending raw articles
loom compile -v ~/my-wiki
loom compile --full -v ~/my-wiki                    # recompile everything

# Ask questions (Claude Code researches your wiki)
loom ask "How does flash attention work?" -v ~/my-wiki
loom ask "Compare RLHF vs DPO" -o markdown -v ~/my-wiki   # save as .md
loom ask "Overview of transformers" -o marp -v ~/my-wiki   # save as slideshow

# Search (BM25-ranked via bb25)
loom search "attention mechanism" -v ~/my-wiki
loom search "attention mechanism" -n 5 -v ~/my-wiki        # limit results

# Rebuild search index from scratch
loom reindex -v ~/my-wiki

# Health check
loom lint -v ~/my-wiki

# Vault info
loom status -v ~/my-wiki

# Open in Obsidian
loom open -v ~/my-wiki                              # opens index
loom open wiki/attention.md -v ~/my-wiki            # opens specific note
```

## Python API

All functions are importable and return dicts/values (no printing, no `sys.exit`).

```python
from mindloom import (
    init_vault, add, compile_vault, ask,
    search, reindex, lint, status,
)

# Create a vault
vault = init_vault("~/my-wiki")            # returns Path

# Ingest a URL (fetch + save to raw/)
result = add(
    "https://arxiv.org/abs/2405.04434",
    vault="~/my-wiki",
    tags=["transformers", "attention"],
    compile_after=True,                    # auto-compile via Claude Code
)
print(result["title"], result["rel_path"]) # "Article Title" "raw/slug.md"

# Compile pending raw articles
compile_vault("~/my-wiki")                 # only uncompiled
compile_vault("~/my-wiki", full=True)      # recompile everything

# Ask questions (Claude Code researches the wiki)
answer = ask("How does flash attention work?", vault="~/my-wiki")
print(answer["answer"])

# Save as markdown or Marp slideshow
ask("Compare RLHF vs DPO", vault="~/my-wiki", output_format="markdown")
ask("Overview of transformers", vault="~/my-wiki", output_format="marp")

# BM25 search
hits = search("attention mechanism", vault="~/my-wiki", limit=5)
for h in hits:
    print(h["title"], h["score"], h["snippet"])

# Rebuild search index
doc_count = reindex("~/my-wiki")

# Health check (writes report to _meta/lint-report.md)
lint("~/my-wiki")

# Vault stats
info = status("~/my-wiki")
print(info)
# {'vault_path': '...', 'raw_count': 12, 'pending_count': 2,
#  'wiki_count': 8, 'output_count': 3, 'has_claude': True}
```

