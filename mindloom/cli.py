import typer
from rich.console import Console
from rich.table import Table

from mindloom import api
from mindloom.vault import VaultNotFoundError, open_in_obsidian

app = typer.Typer(
    name="loom",
    help="Weave raw knowledge into structured Obsidian wikis.",
    no_args_is_help=True,
)
console = Console()

VaultOption = typer.Option(..., "--vault", "-v", help="Path to loom vault")


def _handle_vault_error(e: VaultNotFoundError) -> None:
    console.print(f"[red]{e}[/red]")
    raise typer.Exit(1)


def _handle_claude_error(e: RuntimeError) -> None:
    console.print(f"[yellow]{e}[/yellow]")


# ─── init ────────────────────────────────────────────────────────────────────


@app.command()
def init(
    path: str = typer.Argument(..., help="Where to create the vault"),
) -> None:
    """Create a new vault."""
    vault = api.init_vault(path)
    console.print(f"[green]\u2713 Vault created at {vault}[/green]")


# ─── add ─────────────────────────────────────────────────────────────────────


@app.command()
def add(
    url: str = typer.Argument(..., help="URL to ingest"),
    tags: str = typer.Option("", "--tags", "-t"),
    compile_after: bool = typer.Option(True, "--compile/--no-compile"),
    vault: str = VaultOption,
) -> None:
    """Fetch a URL, save to raw/, compile via Claude Code."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        result = api.add(
            url, vault, tags=tag_list, compile_after=compile_after,
        )
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]\u2713[/green] {result['rel_path']} ({result['title']})"
    )


# ─── compile ─────────────────────────────────────────────────────────────────


@app.command()
def compile(
    full: bool = typer.Option(False, "--full"),
    vault: str = VaultOption,
) -> None:
    """Compile unprocessed raw articles into wiki."""
    try:
        result = api.compile_vault(vault, full=full)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return
    except RuntimeError as e:
        _handle_claude_error(e)
        return

    if result["compiled_count"] == 0:
        console.print("[yellow]Nothing to compile.[/yellow]")
    else:
        console.print(
            f"[bold]Compiled {result['compiled_count']} article(s).[/bold]"
        )


# ─── ask ─────────────────────────────────────────────────────────────────────


@app.command()
def ask(
    question: str = typer.Argument(...),
    output: str = typer.Option("terminal", "--output", "-o"),
    vault: str = VaultOption,
) -> None:
    """Ask a question — Claude Code researches your wiki."""
    fmt = "text" if output == "terminal" else output
    try:
        result = api.ask(question, vault, output_format=fmt)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return
    except RuntimeError as e:
        _handle_claude_error(e)
        return

    if result["answer"]:
        console.print(result["answer"])


# ─── lint ────────────────────────────────────────────────────────────────────


@app.command()
def lint(vault: str = VaultOption) -> None:
    """LLM health checks on the wiki."""
    try:
        result = api.lint(vault)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return
    except RuntimeError as e:
        _handle_claude_error(e)
        return

    if result:
        console.print(result)


# ─── search ──────────────────────────────────────────────────────────────────


@app.command()
def search(
    query: str = typer.Argument(...),
    limit: int = typer.Option(10, "-n"),
    vault: str = VaultOption,
) -> None:
    """BM25 search across all markdown files."""
    try:
        results = api.search(query, vault, limit)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return

    if not results:
        console.print("[yellow]No results.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Title")
    table.add_column("Path")
    table.add_column("Score", width=6)
    table.add_column("Snippet")
    for i, r in enumerate(results, 1):
        snip = (
            r["snippet"]
            .replace(">>>", "[bold yellow]")
            .replace("<<<", "[/bold yellow]")
        )
        table.add_row(str(i), r["title"], r["file"], f"{r['score']:.3f}", snip)
    console.print(table)


@app.command()
def reindex(vault: str = VaultOption) -> None:
    """Rebuild the search corpus from all vault files."""
    try:
        count = api.reindex(vault)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return

    console.print(f"[green]\u2713 Indexed {count} documents.[/green]")


# ─── open, status ───────────────────────────────────────────────────────────


@app.command(name="open")
def open_note(
    path: str = typer.Argument("_index.md"),
    vault: str = VaultOption,
) -> None:
    """Open a note in Obsidian."""
    try:
        v = api.resolve_vault(vault)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return

    open_in_obsidian(v, path)
    console.print(f"[green]\u2713 Opening {path}[/green]")


@app.command()
def status(vault: str = VaultOption) -> None:
    """Vault stats."""
    try:
        s = api.status(vault)
    except VaultNotFoundError as e:
        _handle_vault_error(e)
        return

    console.print(f"[bold]Vault:[/bold] {s['vault_path']}")
    console.print(f"  Raw: {s['raw_count']} ({s['pending_count']} pending)")
    console.print(f"  Wiki: {s['wiki_count']}  Outputs: {s['output_count']}")
    console.print(
        f"  Claude Code: {'[green]\u2713[/green]' if s['has_claude'] else '[red]\u2717[/red]'}"
    )


if __name__ == "__main__":
    app()
