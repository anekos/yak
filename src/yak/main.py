#!/usr/bin/env python

import os
import sys

import click
from openai import OpenAI

from yak.backends.openai import DEFAULT_MODEL, OpenAIBackend
from yak.errors import YakError
from yak.render import render_dictionary


def create_backend(model: str) -> OpenAIBackend:
    api_key = os.environ.get("OPENAI_API_KEY_FOR_YAK")
    if not api_key:
        raise YakError("environment variable OPENAI_API_KEY_FOR_YAK is not set")
    return OpenAIBackend(OpenAI(api_key=api_key), model)


@click.command()
@click.option("--from", "-f", "from_lang", default=None, help="Source language")
@click.option("--to", "-t", "to_lang", default=None, help="Target language")
@click.option("--dictionary", "-d", is_flag=True, help="Dictionary mode")
@click.option("--model", "-m", default=DEFAULT_MODEL, show_default=True)
@click.argument("text", required=False)
def main(
    from_lang: str | None,
    to_lang: str | None,
    dictionary: bool,
    model: str,
    text: str | None,
) -> None:
    """Translate TEXT (or stdin) with OpenAI."""
    try:
        if text is None:
            if sys.stdin.isatty():
                raise YakError("no input text")  # Task 6 で対話モードに置き換える
            text = sys.stdin.read().strip()
        if not text:
            raise YakError("no input text")
        backend = create_backend(model)
        if dictionary:
            click.echo(
                render_dictionary(backend.lookup(text, from_lang, to_lang, None))
            )
        else:
            click.echo(
                backend.translate(text, from_lang, to_lang, None).translated_text
            )
    except YakError as e:
        click.echo(f"yak: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
