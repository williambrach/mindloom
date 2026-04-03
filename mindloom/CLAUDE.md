# Knowledge Base — Claude Code Instructions

You are maintaining an Obsidian-compatible knowledge base powered by mindloom.
Your job is to compile raw web content into a structured, interlinked wiki.
The wiki is YOUR domain — the user rarely edits it directly.

## Vault structure

```
.
├── raw/           ← Ingested web content (don't modify these)
├── wiki/          ← YOUR compiled articles (you own this)
├── mocs/          ← Maps of Content (auto-generated indexes)
├── outputs/       ← Q&A answers, slideshows, charts
├── attachments/   ← Images organized by article slug
├── _meta/         ← System files (db, lint reports)
├── _index.md      ← Master index (you maintain this)
└── CLAUDE.md      ← This file
```

## Frontmatter schema

Every wiki article MUST have this YAML frontmatter:

```yaml
---
title: "Article Title"
aliases: ["Short Name", "Abbreviation"]
tags: [topic/machine-learning, status/published]
summary: "One-sentence summary for the index."
sources: ["raw-slug-1", "raw-slug-2"]
created: "2026-04-03T14:00:00Z"
updated: "2026-04-03T14:00:00Z"
---
```

Tags use nested namespaces: `topic/`, `status/` (raw|draft|published), `source/` (article|paper|video|repo).

## Compilation rules

When you receive a new raw article to compile:

1. **Read the raw article** completely.
2. **Read `_index.md`** to understand what wiki articles already exist.
3. **Search for related content**: run `loom search "<key terms>"` first. If the results are relevant, read those files. If not, fall back to Grep on `wiki/`, `raw/`, and `outputs/`.
4. **Decide**: CREATE a new wiki article, or UPDATE an existing one.
   - If >70% of the content overlaps an existing article → UPDATE
   - If the topic is genuinely new → CREATE
   - If two existing articles should merge → MERGE (update one, redirect the other)
5. **Write the article** following the format below.
6. **Add wikilinks**: scan your article for mentions of other wiki article titles and wrap them in `[[wikilinks]]`. Also add wikilinks FROM related existing articles back to your new one.
7. **Update `_index.md`**: add the new article between the `<!-- BEGIN:ARTICLES -->` and `<!-- END:ARTICLES -->` markers.
8. **Mark as compiled**: change the raw article's frontmatter `status: raw` → `status: compiled`.

## Article format

```markdown
---
(frontmatter as above)
---

## Summary

(2-3 sentence overview. This is what appears in the index.)

## Key concepts

(Main content organized with ## headings. Link to [[other articles]].)

## Details

(Deeper explanation, examples, formulas, code, etc.)

## Sources

- Raw: [[raw/slug-name]]
- External: [Original URL](https://...)
```

## Wikilink conventions

- Use `[[article-title]]` for internal links (Obsidian resolves by filename).
- For display text: `[[filename|Display Text]]`.
- For section links: `[[filename#Section Name]]`.
- Images: `![alt](attachments/slug/hash.png)` (standard markdown, not wikilink).

## Index maintenance

The `_index.md` file has marker comments. Only edit between them:

```markdown
<!-- BEGIN:ARTICLES -->
- [[wiki/article-name|Article Title]] — One-sentence summary
<!-- END:ARTICLES -->
```

Keep entries sorted alphabetically. The RECENT section lists the 10 most recently updated.

## Linting rules

When asked to lint, check:

1. **Broken links**: every `[[target]]` must have a corresponding .md file
2. **Orphans**: wiki articles with zero inbound wikilinks
3. **Stale sources**: raw/ files still with `status: raw` in frontmatter
4. **Missing metadata**: articles without summary, tags, or sources
5. **Duplicates**: articles with >70% content overlap (suggest merge)
6. **Missing concepts**: terms in 3+ articles that lack their own page
7. **Consistency**: same fact stated differently across articles

Write results to `_meta/lint-report.md`.

## Q&A rules

When answering questions:

1. Always start by reading `_index.md`.
2. Run `loom search "<relevant terms>"` first. If the results look useful, read those files. If not, fall back to Grep on `wiki/`, `raw/`, and `outputs/`.
3. Read the full text of the top 3-5 relevant articles.
4. Cite sources with `[[wikilinks]]`.
5. If the wiki doesn't have enough info, say so clearly.
6. When asked for Marp slides, use `marp: true` frontmatter and `---` between slides.
7. When saving output, write to `outputs/` with proper frontmatter.

## Tools available to you

- **`loom search "<query>" -n <limit>`** — BM25 keyword search across all vault files (wiki/, raw/, outputs/). Run via Bash. **Use this first** when looking for content in the knowledge base. It returns ranked results with titles, scores, and highlighted snippets. If the results are relevant, read the matched files directly. If they are not useful (low scores, off-topic), fall back to Grep/Glob.
- Grep — search content across all .md files (use glob `*.md` and search in `wiki/`, `raw/`, `outputs/`). Use as fallback when loom search misses exact patterns or regex is needed.
- Glob — find files by name pattern (e.g., `wiki/*.md`)
- Direct file read/write — read any .md file, write to wiki/, mocs/, outputs/
- To mark a raw article as compiled, change its frontmatter `status: raw` → `status: compiled`

## Style guide

- Clear, encyclopedic prose. Not marketing, not academic jargon.
- Active voice. Define technical terms on first use.
- Summaries under 3 sentences.
- One concept per article — split if too broad.
- Concrete examples over abstract explanations.