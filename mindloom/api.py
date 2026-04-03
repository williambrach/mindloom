"""Public Python API for mindloom.

All functions are importable and return values instead of printing to console.
Errors are raised as exceptions (RuntimeError) instead of calling sys.exit().
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from mindloom.claude import has_claude_code, run_claude
from mindloom.search import (
    add_to_corpus,
    reindex_corpus,
    sync_corpus,
)
from mindloom.search import (
    search as bm25_search,
)
from mindloom.vault import (
    LOOM_MARKER,
    read_frontmatter,
    resolve_vault,
    slugify,
)

logger = logging.getLogger("mindloom")


# ─── internal helpers ────────────────────────────────────────────────────────


def _extract_pdf(
    url: str, vault: Path,
) -> tuple[str, str, str, str]:
    """Download a PDF and extract markdown + metadata via pymupdf4llm."""
    import tempfile

    import httpx
    import pymupdf
    import pymupdf4llm

    resp = httpx.get(url, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        md = pymupdf4llm.to_markdown(
            tmp_path,
            write_images=True,
            image_path=str(vault / "attachments"),
        )
        doc = pymupdf.open(tmp_path)
        meta = doc.metadata or {}
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    meta_title = meta.get("title", "").strip()
    url_path = urlparse(url).path
    filename_from_url = url_path.split("/")[-1]
    title = meta_title or filename_from_url
    author = meta.get("author", "").strip()
    date = meta.get("creationDate", "").strip()

    return md, title, author, date


_JS_SHELL_MARKERS = [
    'id="root"',
    'id="app"',
    'id="__next"',
    'id="__nuxt"',
    "data-reactroot",
    "ng-app",
    "ng-version",
    "data-server-rendered",
]


def _is_js_shell(html: str) -> bool:
    """Detect if HTML is a JS framework shell with little real content."""
    body_match = re.search(
        r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE
    )
    body = body_match.group(1) if body_match else html
    text = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text).strip()
    if len(text) < 200:
        return True
    return any(marker in html for marker in _JS_SHELL_MARKERS)


def _fetch_with_browser(url: str) -> str | None:
    """Fetch page HTML using Playwright (headless Chromium)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "Playwright not installed. "
            "Install: uv pip install 'mindloom[browser]' "
            "&& playwright install chromium"
        )
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30_000)
        html = page.content()
        browser.close()
    return html


def _trafilatura_extract(html: str) -> tuple[str | None, str, str, str]:
    """Run trafilatura extraction and return (md, title, author, date)."""
    import trafilatura

    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_images=True,
        include_tables=True,
        include_links=True,
    )
    raw_meta = trafilatura.bare_extraction(html)
    title = getattr(raw_meta, "title", None) or ""
    author = getattr(raw_meta, "author", "") or ""
    date = getattr(raw_meta, "date", "") or ""
    return md, title, author, date


def _extract_html(url: str) -> tuple[str, str, str, str, str]:
    """Fetch HTML page, extract markdown + metadata.

    Returns (md, title, author, date, fetch_method).
    Raises RuntimeError on failure.
    """
    import markdownify
    import trafilatura

    fetch_method = "trafilatura"

    html = trafilatura.fetch_url(url)

    if not html:
        html = _fetch_with_browser(url)
        fetch_method = "browser"
        if not html:
            raise RuntimeError(
                f"Failed to fetch {url} (tried trafilatura + browser)."
            )

    md, title, author, date = _trafilatura_extract(html)
    title = title or urlparse(url).netloc

    if not md or len(md) < 100:
        if fetch_method == "trafilatura" and _is_js_shell(html):
            browser_html = _fetch_with_browser(url)
            if browser_html:
                html = browser_html
                fetch_method = "browser"
                md2, t2, a2, d2 = _trafilatura_extract(html)
                if md2 and len(md2) >= 100:
                    md = md2
                    title = t2 or title
                    author = a2 or author
                    date = d2 or date

        if not md or len(md) < 100:
            md = markdownify.markdownify(
                html, heading_style="ATX", strip=["script", "style"]
            )
            fetch_method += "+markdownify"

    logger.info("fetch method: %s", fetch_method)
    return md, title, author, date, fetch_method


def _download_images(
    markdown: str, base_url: str, img_dir: Path, slug: str,
) -> str:
    """Download images referenced in markdown and rewrite paths."""
    import httpx

    def repl(m: re.Match[str]) -> str:
        alt, src = m.group(1), m.group(2)
        if src.startswith("data:"):
            return m.group(0)
        try:
            absolute_url = urljoin(base_url, src)
            r = httpx.get(absolute_url, timeout=10, follow_redirects=True)
            r.raise_for_status()
            parsed_path = urlparse(absolute_url).path
            ext = Path(parsed_path).suffix or ".png"
            digest = hashlib.sha256(r.content).hexdigest()
            content_hash = digest[:12]
            fname = f"{content_hash}{ext}"
            (img_dir / fname).write_bytes(r.content)
            return f"![{alt}](attachments/{slug}/{fname})"
        except Exception:
            return m.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)


# ─── public API ──────────────────────────────────────────────────────────────


def init_vault(path: str) -> Path:
    """Create a new vault. Returns the resolved vault path."""
    vault = Path(path).expanduser().resolve()
    for d in ["raw", "wiki", "mocs", "outputs", "attachments", "_meta"]:
        (vault / d).mkdir(parents=True, exist_ok=True)

    (vault / LOOM_MARKER).write_text(
        json.dumps(
            {"created": datetime.now(UTC).isoformat(), "version": 1},
            indent=2,
        )
    )

    claude_md = Path(__file__).parent / "CLAUDE.md"
    if claude_md.exists():
        shutil.copy(claude_md, vault / "CLAUDE.md")

    (vault / "_index.md").write_text(textwrap.dedent("""\
        ---
        title: Knowledge Base Index
        tags: [moc/root]
        ---
        # Knowledge base

        ## All articles
        <!-- BEGIN:ARTICLES -->
        _Run `loom add <url>` to get started._
        <!-- END:ARTICLES -->

        ## Recent
        <!-- BEGIN:RECENT -->
        <!-- END:RECENT -->
    """))

    return vault


def add(
    url: str,
    vault: str,
    tags: list[str] | None = None,
    compile_after: bool = False,
) -> dict[str, Any]:
    """Fetch a URL, save to raw/.

    Returns dict with keys: rel_path, title, author, date, fetch_method, tags.
    Raises RuntimeError on fetch failure or if compile needs Claude and it's missing.
    """
    import httpx

    v = resolve_vault(vault)
    tag_list = tags or []

    url_path = urlparse(url).path.lower()
    is_pdf = url_path.endswith(".pdf")
    if not is_pdf:
        head = httpx.head(url, follow_redirects=True, timeout=10)
        is_pdf = "application/pdf" in head.headers.get("content-type", "")

    if is_pdf:
        md, title, author, date = _extract_pdf(url, v)
        fetch_method = "pdf"
    else:
        md, title, author, date, fetch_method = _extract_html(url)

    digest = hashlib.md5(url.encode()).hexdigest()
    url_hash = digest[:6]
    slug = f"{slugify(title)}-{url_hash}"
    img_dir = v / "attachments" / slug
    img_dir.mkdir(parents=True, exist_ok=True)

    if not is_pdf:
        md = _download_images(md, url, img_dir, slug)

    rel_path = f"raw/{slug}.md"
    raw_path = v / "raw" / f"{slug}.md"
    raw_path.write_text(textwrap.dedent(f"""\
        ---
        title: "{title}"
        source: "{url}"
        author: "{author}"
        date: "{date}"
        fetched: "{datetime.now(UTC).isoformat()}"
        tags: {json.dumps(tag_list)}
        fetch_method: "{fetch_method}"
        status: raw
        ---

    """) + md)

    add_to_corpus(v, rel_path)

    result: dict[str, Any] = {
        "rel_path": rel_path,
        "title": title,
        "author": author,
        "date": date,
        "fetch_method": fetch_method,
        "tags": tag_list,
    }

    if compile_after:
        compile_result = compile_vault(
            vault,
            articles=[rel_path],
            _title=title,
            _tags=tag_list,
        )
        result["compile_output"] = compile_result.get("output")

    return result


def compile_vault(
    vault: str,
    full: bool = False,
    articles: list[str] | None = None,
    _title: str | None = None,
    _tags: list[str] | None = None,
) -> dict[str, Any]:
    """Compile raw articles into wiki via Claude Code.

    Returns dict with keys: compiled_count, articles, output.
    Raises RuntimeError if Claude Code is not installed.
    """
    v = resolve_vault(vault)
    raw_dir = v / "raw"

    if articles:
        pending_names = articles
    elif not raw_dir.exists():
        return {"compiled_count": 0, "articles": [], "output": None}
    elif full:
        pending = list(raw_dir.glob("*.md"))
        pending_names = [f"raw/{f.name}" for f in pending]
    else:
        pending = [
            f
            for f in raw_dir.glob("*.md")
            if read_frontmatter(f).get("status") == "raw"
        ]
        pending_names = [f"raw/{f.name}" for f in pending]

    if not pending_names:
        return {"compiled_count": 0, "articles": [], "output": None}

    # If called from add() with a single article, use the targeted prompt
    if _title and len(pending_names) == 1:
        prompt = textwrap.dedent(f"""\
            New article ingested at {pending_names[0]} — "{_title}" (tags: {', '.join(_tags or [])})

            Follow CLAUDE.md to:
            1. Read the raw article
            2. Create or update a wiki article in wiki/
            3. Update _index.md
            4. Add [[wikilinks]] to related articles
            5. Change raw article frontmatter status to "compiled"
        """)
    else:
        names = "\n".join(f"  - {n}" for n in pending_names)
        prompt = textwrap.dedent(f"""\
            {len(pending_names)} uncompiled articles:
            {names}

            For each, follow CLAUDE.md:
            1. Read raw article → create/update wiki article
            2. Add [[wikilinks]], update _index.md
            3. Set raw frontmatter status to "compiled"
        """)

    output = run_claude(
        v, prompt,
        max_turns=len(pending_names) * 5 + 10,
        stream=False,
    )
    sync_corpus(v)

    return {
        "compiled_count": len(pending_names),
        "articles": pending_names,
        "output": output,
    }


def search(query: str, vault: str, limit: int = 10) -> list[dict[str, Any]]:
    """BM25 search across all markdown files.

    Returns list of dicts with keys: file, title, snippet, score.
    """
    v = resolve_vault(vault)
    return bm25_search(v, query, limit)


def reindex(vault: str) -> int:
    """Rebuild the search corpus from all vault files. Returns doc count."""
    v = resolve_vault(vault)
    return reindex_corpus(v)


def ask(
    question: str,
    vault: str,
    output_format: str = "text",
) -> dict[str, Any]:
    """Ask a question — Claude Code researches the wiki.

    output_format: "text", "markdown", or "marp".
    Returns dict with keys: answer, output_path.
    Raises RuntimeError if Claude Code is not installed.
    """
    v = resolve_vault(vault)
    extra = ""
    output_path = None

    if output_format == "marp":
        extra = "Format as Marp slideshow."
    elif output_format == "markdown":
        extra = "Format as markdown article."

    if output_format != "text":
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{ts}-{slugify(question[:30])}.md"
        extra += f" Save to outputs/{filename}"
        output_path = f"outputs/{filename}"

    answer = run_claude(
        v,
        textwrap.dedent(f"""\
            Research the wiki and answer: {question}

            1. Read _index.md
            2. Use Grep to search wiki/, raw/, outputs/ for relevant articles
            3. Read top articles, synthesize answer with [[wikilinks]]
            {extra}
        """),
        stream=False,
    )

    return {"answer": answer, "output_path": output_path}


def lint(vault: str) -> str | None:
    """LLM health checks on the wiki.

    Returns Claude output string, or None if nothing to report.
    Raises RuntimeError if Claude Code is not installed.
    """
    v = resolve_vault(vault)
    output = run_claude(
        v,
        textwrap.dedent("""\
            Audit the wiki per CLAUDE.md linting rules.
            Check: broken links, orphans, stale raw articles, missing metadata,
            overlaps to merge, missing concept pages, and suggest next questions.
            Write report to _meta/lint-report.md.
        """),
        max_turns=20,
        stream=False,
    )
    return output


def status(vault: str) -> dict[str, Any]:
    """Vault stats.

    Returns dict with keys: vault_path, raw_count, pending_count,
    wiki_count, output_count, has_claude.
    """
    v = resolve_vault(vault)

    raw_dir = v / "raw"
    raw = list(raw_dir.glob("*.md")) if raw_dir.exists() else []
    pending = [f for f in raw if read_frontmatter(f).get("status") == "raw"]

    wiki_dir = v / "wiki"
    wiki_files = list(wiki_dir.glob("*.md")) if wiki_dir.exists() else []

    outputs_dir = v / "outputs"
    output_files = (
        list(outputs_dir.glob("*.md")) if outputs_dir.exists() else []
    )

    return {
        "vault_path": str(v),
        "raw_count": len(raw),
        "pending_count": len(pending),
        "wiki_count": len(wiki_files),
        "output_count": len(output_files),
        "has_claude": has_claude_code(),
    }
