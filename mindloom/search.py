import json
import re
import tempfile
from pathlib import Path

import bb25 as bb
import tiktoken

from mindloom.vault import read_body, read_frontmatter

CORPUS_FILE = "_meta/corpus.jsonl"
DUMMY_EMBEDDING = [0.0] * 8
SEARCH_DIRS = ("wiki", "raw", "outputs")

_enc = tiktoken.get_encoding("cl100k_base")


def tokenize(text: str) -> list[str]:
    """Tokenize text using tiktoken, then extract word-level tokens."""
    ids = _enc.encode(text)
    words: list[str] = []
    current: list[str] = []
    for tid in ids:
        s = _enc.decode([tid])
        if s and s[0] == " " and current:
            words.extend(re.findall(r"\w+", "".join(current).lower()))
            current = [s.lstrip()]
        else:
            current.append(s)
    if current:
        words.extend(re.findall(r"\w+", "".join(current).lower()))
    return words


def _corpus_path(vault: Path) -> Path:
    return vault / CORPUS_FILE


def _scan_vault_files(vault: Path) -> dict[str, Path]:
    """Return {rel_path: absolute_path} for all .md files in searchable dirs."""
    files: dict[str, Path] = {}
    for sub in SEARCH_DIRS:
        d = vault / sub
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            files[f"{sub}/{f.name}"] = f
    return files


def _load_corpus_records(vault: Path) -> dict[str, dict]:
    """Load existing corpus.jsonl into {doc_id: record} dict."""
    cp = _corpus_path(vault)
    if not cp.exists():
        return {}
    records: dict[str, dict] = {}
    for line in cp.read_text().splitlines():
        if line.strip():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or "doc_id" not in rec:
                continue
            records[rec["doc_id"]] = rec
    return records


def _write_corpus_records(vault: Path, records: dict[str, dict]) -> None:
    cp = _corpus_path(vault)
    cp.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records.values()]
    content = ("\n".join(lines) + "\n") if lines else ""
    # Atomic write: write to temp file then rename, so interrupted writes
    # don't leave a corrupt corpus.jsonl
    fd, tmp = tempfile.mkstemp(dir=cp.parent, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp).replace(cp)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _make_record(doc_id: str, path: Path) -> dict:
    fm = read_frontmatter(path)
    body = read_body(path)
    title = fm.get("title", path.stem)
    return {"doc_id": doc_id, "title": title, "text": body}


def add_to_corpus(vault: Path, rel_path: str) -> None:
    """Add a single file to the corpus. Skips if already present."""
    records = _load_corpus_records(vault)
    if rel_path in records:
        return
    abs_path = vault / rel_path
    if not abs_path.exists():
        return
    records[rel_path] = _make_record(rel_path, abs_path)
    _write_corpus_records(vault, records)


def sync_corpus(vault: Path) -> int:
    """Sync corpus.jsonl with actual vault files. Returns number of changes."""
    vault_files = _scan_vault_files(vault)
    records = _load_corpus_records(vault)

    changes = 0

    # Add missing files
    for rel, abs_path in vault_files.items():
        if rel not in records:
            records[rel] = _make_record(rel, abs_path)
            changes += 1

    # Remove deleted files
    stale = [doc_id for doc_id in records if doc_id not in vault_files]
    for doc_id in stale:
        del records[doc_id]
        changes += 1

    if changes:
        _write_corpus_records(vault, records)
    return changes


def reindex_corpus(vault: Path) -> int:
    """Full rebuild of corpus.jsonl from scratch."""
    vault_files = _scan_vault_files(vault)
    records: dict[str, dict] = {}
    for rel, abs_path in vault_files.items():
        records[rel] = _make_record(rel, abs_path)
    _write_corpus_records(vault, records)
    return len(records)


def search(vault: Path, query: str, limit: int = 10) -> list[dict]:
    """BM25 search across the corpus. Returns ranked results with snippets."""
    sync_corpus(vault)

    records = _load_corpus_records(vault)
    if not records:
        return []

    # Build bb25 corpus
    corpus = bb.Corpus()
    for rec in records.values():
        corpus.add_document(rec["doc_id"], rec["text"], DUMMY_EMBEDDING)
    corpus.build_index()

    # Score with BayesianBM25
    bm25 = bb.BM25Scorer(corpus, k1=1.2, b=0.75)
    bayesian = bb.BayesianBM25Scorer(bm25, 1.0, 0.5)

    terms = tokenize(query)
    docs = corpus.documents()

    scored = []
    for doc in docs:
        score = bayesian.score(terms, doc)
        if score > 0:
            scored.append((doc.id, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Build results with snippets
    results = []
    escaped_terms = "|".join(re.escape(t) for t in terms)
    pat = re.compile(escaped_terms, re.IGNORECASE)

    for doc_id, score in scored[:limit]:
        rec = records[doc_id]
        text = rec["text"]
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            snippet = text[start:end].replace("\n", " ").strip()
            snippet = pat.sub(lambda x: f">>>{x.group(0)}<<<", snippet)
        else:
            snippet = text[:120].replace("\n", " ").strip()

        results.append({
            "file": doc_id,
            "title": rec["title"],
            "snippet": snippet,
            "score": score,
        })

    return results
