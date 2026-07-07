from pathlib import Path

import diskcache
from platformdirs import user_cache_dir

from yak.backends.base import DictionaryProvider, ModeClassifier, Translator
from yak.errors import YakError
from yak.models import DictionaryResult, ModeDecision, TranslationResult

CACHE_SIZE_LIMIT = 100 * 1024 * 1024  # 100MB


def cache_directory() -> Path:
    return Path(user_cache_dir("yak"))


def open_cache() -> diskcache.Cache:
    return diskcache.Cache(str(cache_directory()), size_limit=CACHE_SIZE_LIMIT)


def clear_cache() -> int:
    with open_cache() as cache:
        count: int = cache.clear()
        return count


class CachingBackend:
    """任意のバックエンドを包み、結果を diskcache に永続キャッシュするラッパー。

    値は model_dump() した dict で保存する(クラス定義の pickle に依存させない)。
    モデルのスキーマを変更する場合は namespace を変えるか手動でキャッシュをクリアする必要がある。
    """

    def __init__(
        self,
        inner: Translator | DictionaryProvider | ModeClassifier,
        cache: diskcache.Cache,
        *,
        namespace: str,
        read_enabled: bool = True,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._namespace = namespace
        self._read_enabled = read_enabled

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        key = (
            "translate",
            self._namespace,
            text,
            from_lang,
            to_lang,
            extra_instruction,
        )
        if self._read_enabled:
            cached = self._cache.get(key)
            if cached is not None:
                return TranslationResult.model_validate(cached)
        if not isinstance(self._inner, Translator):
            raise YakError("this backend does not support translation mode")
        result = self._inner.translate(text, from_lang, to_lang, extra_instruction)
        self._cache[key] = result.model_dump()
        return result

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult:
        key = (
            "lookup",
            self._namespace,
            text,
            from_lang,
            to_lang,
            extra_instruction,
        )
        if self._read_enabled:
            cached = self._cache.get(key)
            if cached is not None:
                return DictionaryResult.model_validate(cached)
        if not isinstance(self._inner, DictionaryProvider):
            raise YakError("this backend does not support dictionary mode")
        result = self._inner.lookup(text, from_lang, to_lang, extra_instruction)
        self._cache[key] = result.model_dump()
        return result

    def classify(self, text: str) -> ModeDecision:
        key = ("classify", self._namespace, text, None, None, None)
        if self._read_enabled:
            cached = self._cache.get(key)
            if cached is not None:
                return ModeDecision.model_validate(cached)
        if not isinstance(self._inner, ModeClassifier):
            raise YakError("this backend does not support mode classification")
        result = self._inner.classify(text)
        self._cache[key] = result.model_dump()
        return result
