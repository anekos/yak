from pathlib import Path

import diskcache
import pytest

from tests.test_cli import FakeBackend
from tests.test_interactive import TranslateOnlyBackend
from yak.cache import CachingBackend
from yak.errors import YakError
from yak.models import DictionaryResult, Pronunciation


def _make_cache(tmp_path: Path) -> diskcache.Cache:
    return diskcache.Cache(str(tmp_path / "cache"))


class LookupOnlyBackend:
    """`translate` を持たない、辞書専用のバックエンド。"""

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult:
        return DictionaryResult(
            meanings=["test"],
            pronunciation=Pronunciation(katakana="テスト", ipa="/test/"),
            examples=["test example"],
        )


def test_second_translate_hits_cache(tmp_path: Path) -> None:
    backend = FakeBackend()
    caching = CachingBackend(backend, _make_cache(tmp_path), namespace="test")
    first = caching.translate("hello", None, None, None)
    second = caching.translate("hello", None, None, None)
    assert first == second
    assert len(backend.translate_calls) == 1


def test_second_lookup_hits_cache(tmp_path: Path) -> None:
    backend = FakeBackend()
    caching = CachingBackend(backend, _make_cache(tmp_path), namespace="test")
    first = caching.lookup("cat", None, None, None)
    second = caching.lookup("cat", None, None, None)
    assert first == second
    assert len(backend.lookup_calls) == 1


def test_translate_and_lookup_use_separate_entries(tmp_path: Path) -> None:
    backend = FakeBackend()
    caching = CachingBackend(backend, _make_cache(tmp_path), namespace="test")
    caching.translate("cat", None, None, None)
    caching.lookup("cat", None, None, None)
    assert len(backend.translate_calls) == 1
    assert len(backend.lookup_calls) == 1


def test_different_languages_are_separate_entries(tmp_path: Path) -> None:
    backend = FakeBackend()
    caching = CachingBackend(backend, _make_cache(tmp_path), namespace="test")
    caching.translate("hello", None, "French", None)
    caching.translate("hello", None, "German", None)
    assert len(backend.translate_calls) == 2


def test_different_extra_instructions_are_separate_entries(tmp_path: Path) -> None:
    backend = FakeBackend()
    caching = CachingBackend(backend, _make_cache(tmp_path), namespace="test")
    caching.translate("hello", None, None, None)
    caching.translate("hello", None, None, "Use polite form.")
    assert len(backend.translate_calls) == 2


def test_different_namespaces_are_separate_entries(tmp_path: Path) -> None:
    backend = FakeBackend()
    cache = _make_cache(tmp_path)
    a = CachingBackend(backend, cache, namespace="openai:model-a")
    b = CachingBackend(backend, cache, namespace="openai:model-b")
    a.translate("hello", None, None, None)
    b.translate("hello", None, None, None)
    assert len(backend.translate_calls) == 2


def test_read_disabled_always_calls_inner_but_still_writes(tmp_path: Path) -> None:
    backend = FakeBackend()
    cache = _make_cache(tmp_path)
    no_read = CachingBackend(backend, cache, namespace="test", read_enabled=False)
    no_read.translate("hello", None, None, None)
    no_read.translate("hello", None, None, None)
    assert len(backend.translate_calls) == 2
    reader = CachingBackend(backend, cache, namespace="test")
    reader.translate("hello", None, None, None)
    assert len(backend.translate_calls) == 2


def test_lookup_with_translate_only_inner_raises(tmp_path: Path) -> None:
    caching = CachingBackend(
        TranslateOnlyBackend(), _make_cache(tmp_path), namespace="test"
    )
    with pytest.raises(YakError, match="dictionary mode"):
        caching.lookup("word", None, None, None)


def test_translate_with_lookup_only_inner_raises(tmp_path: Path) -> None:
    caching = CachingBackend(
        LookupOnlyBackend(), _make_cache(tmp_path), namespace="test"
    )
    with pytest.raises(YakError, match="translation mode"):
        caching.translate("hello", None, None, None)
