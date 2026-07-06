from typing import Protocol

from yak.models import DictionaryResult, TranslationResult


class Translator(Protocol):
    """翻訳バックエンドの共通インターフェイス。

    Google 翻訳などの非 LLM バックエンドはこれのみ実装する。
    """

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult: ...


class DictionaryProvider(Protocol):
    """辞書モードを提供できるバックエンドのインターフェイス。"""

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult: ...
