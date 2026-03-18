"""markdown2confluence -- Convert GitHub Flavored Markdown files to Confluence pages."""

from pathlib import Path

import click

from lib.alerts import preprocess_alerts
from lib.mermaid import preprocess_mermaid
from lib.parser import create_parser, preprocess_images


def parse_file(input_path):
    """Parse a Markdown file to a token list."""
    input_path = Path(input_path)
    md_text = input_path.read_text(encoding="utf-8")

    md = create_parser()
    tokens = md(md_text)

    tokens = preprocess_mermaid(tokens, str(input_path.parent))
    tokens = preprocess_alerts(tokens)
    tokens = preprocess_images(tokens)

    return tokens


@click.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    default="./output",
    type=click.Path(),
    help="Output directory for temporary files (default: ./output)",
)
@click.option(
    "--page-id",
    default=None,
    help="ID of an existing Confluence page to update.",
)
@click.option(
    "--parent-id",
    default=None,
    help="ID of the parent Confluence page under which to create a new page.",
)
@click.option(
    "--space-key",
    default=None,
    help="Confluence space key (required when creating a new page).",
)
def main(files, output, page_id, parent_id, space_key):
    """Convert one or more Markdown files to Confluence pages."""
    if not page_id and not parent_id:
        raise click.UsageError("One of --page-id or --parent-id is required.")

    for f in files:
        tokens = parse_file(f)
        token_types = [t["type"] for t in tokens]
        click.echo(f"Parsed: {f}")
        click.echo(f"  Top-level tokens ({len(tokens)}): {token_types}")


if __name__ == "__main__":
    main()
