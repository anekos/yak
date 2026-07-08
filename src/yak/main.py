#!/usr/bin/env python

import os
import sys

import click
from openai import OpenAI

from yak.backends.base import DictionaryProvider
from yak.backends.openai import (
    DEFAULT_CLASSIFIER_MODEL,
    DEFAULT_MODEL,
    OpenAIBackend,
)
from yak.cache import CachingBackend, clear_cache, open_cache
from yak.errors import YakError
from yak.interactive import InteractiveSession, Mode, run_interactive
from yak.render import oneline_text, render_dictionary


def create_backend(model: str, *, read_cache: bool = True) -> CachingBackend:
    api_key = os.environ.get("OPENAI_API_KEY_FOR_YAK")
    if not api_key:
        raise YakError("environment variable OPENAI_API_KEY_FOR_YAK is not set")
    inner = OpenAIBackend(OpenAI(api_key=api_key), model)
    return CachingBackend(
        inner,
        open_cache(),
        namespace=f"openai:{model}",
        read_enabled=read_cache,
    )


def create_classifier(model: str, *, read_cache: bool = True) -> CachingBackend:
    """モード自動判定用バックエンド。テストから独立に差し替えられるよう分離する。"""
    return create_backend(model, read_cache=read_cache)


@click.command()
@click.option("--from", "-f", "from_lang", default=None, help="Source language")
@click.option("--to", "-t", "to_lang", default=None, help="Target language")
@click.option("--dictionary", "-d", is_flag=True, help="Force dictionary mode")
@click.option("--translator", is_flag=True, help="Force translation mode")
@click.option(
    "--model",
    "-m",
    envvar="YAK_MODEL",
    default=DEFAULT_MODEL,
    show_default=True,
    help="OpenAI model",
)
@click.option(
    "--classifier-model",
    envvar="YAK_CLASSIFIER_MODEL",
    default=DEFAULT_CLASSIFIER_MODEL,
    show_default=True,
    help="OpenAI model for mode auto-detection",
)
@click.option(
    "--no-cache", is_flag=True, help="Bypass cache reads (results are still saved)"
)
@click.option(
    "--clear-cache", "clear_cache_flag", is_flag=True, help="Clear the cache and exit"
)
@click.option("--oneline", "-1", "oneline", is_flag=True, help="Output a single line")
@click.argument("text", required=False)
def main(
    from_lang: str | None,
    to_lang: str | None,
    dictionary: bool,
    translator: bool,
    model: str,
    classifier_model: str,
    no_cache: bool,
    clear_cache_flag: bool,
    oneline: bool,
    text: str | None,
) -> None:
    """Translate TEXT (or stdin) with OpenAI."""
    try:
        if clear_cache_flag:
            count = clear_cache()
            click.echo(f"キャッシュをクリアしました ({count} 件)")
            return
        if dictionary and translator:
            raise YakError("cannot use --dictionary and --translator together")
        mode: Mode = (
            "dictionary" if dictionary else "translation" if translator else "auto"
        )
        if text is None:
            if sys.stdin.isatty():
                backend = create_backend(model, read_cache=not no_cache)
                classifier = (
                    create_classifier(classifier_model, read_cache=not no_cache)
                    if mode == "auto"
                    else None
                )
                run_interactive(
                    InteractiveSession(
                        backend,
                        mode=mode,
                        classifier=classifier,
                        from_lang=from_lang,
                        to_lang=to_lang,
                        oneline=oneline,
                    )
                )
                return
            text = sys.stdin.read().strip()
        if not text:
            raise YakError("no input text")
        backend = create_backend(model, read_cache=not no_cache)
        if mode == "auto":
            classifier = create_classifier(classifier_model, read_cache=not no_cache)
            use_dictionary = classifier.classify(text).is_dictionary_entry
        else:
            use_dictionary = mode == "dictionary"
        if use_dictionary:
            if not isinstance(backend, DictionaryProvider):
                raise YakError("this backend does not support dictionary mode")
            click.echo(
                render_dictionary(
                    backend.lookup(text, from_lang, to_lang, None),
                    oneline=oneline,
                )
            )
        else:
            translated = backend.translate(
                text, from_lang, to_lang, None
            ).translated_text
            click.echo(oneline_text(translated) if oneline else translated)
    except YakError as e:
        click.echo(f"yak: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
