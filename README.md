# mindloom

Weave raw knowledge into structured Obsidian wikis, powered by Claude Code.

Inspired by [Andrej Karpathy's LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595) workflow.
You curate (paste a link). Claude Code thinks (compile, cross-link, answer, lint).

## Install

```bash
# Recommended: global install via uv (works from anywhere)
uv tool install mindloom
```

## How it works

```
loom add <url>
  ├─ 1. trafilatura fetches + converts to markdown       (Python)
  ├─ 2. images downloaded, paths rewritten                (Python)
  ├─ 3. saved to raw/ with YAML frontmatter               (Python)
  └─ 4. claude -p "compile this into the wiki"            (Claude Code)
         ├─ reads CLAUDE.md (the rules)
         ├─ reads _index.md (what exists)
         ├─ uses Grep to find related articles
         ├─ writes/updates wiki/ articles with [[wikilinks]]
         └─ updates _index.md
```

## Usage

```bash
# Create a vault (open it in Obsidian)
loom init ~/my-wiki

# Add articles — fetches + auto-compiles
loom add "https://arxiv.org/abs/..." -t "transformers, attention"
loom add "https://blog.example.com" -t "rl, rlhf"
loom add "https://..." --no-compile       # just fetch, compile later

# Compile pending raw articles
loom compile
loom compile --full                        # recompile everything

# Ask questions (Claude Code researches your wiki)
loom ask "How does flash attention work?"
loom ask "Compare RLHF vs DPO" -o markdown  # save as .md file
loom ask "Overview of transformers" -o marp  # save as slideshow

# Search (BM25-ranked via bb25)
loom search "attention mechanism"

# Rebuild search index from scratch
loom reindex

# Health check
loom lint

# Vault info
loom status

# Open in Obsidian
loom open                                  # opens index
loom open wiki/attention.md                # opens specific note
```

## Vault resolution

Every command requires the `--vault /path` flag (or `-v`) pointing to your vault directory:

```bash
loom add "https://..." -v ~/my-wiki
```

