from yak.models import DictionaryResult, Pronunciation, TranslationResult


def test_translation_result_fields() -> None:
    result = TranslationResult(
        detected_source_language="English",
        translated_text="こんにちは",
    )
    assert result.translated_text == "こんにちは"
    assert result.detected_source_language == "English"


def test_dictionary_result_fields() -> None:
    result = DictionaryResult(
        meanings=["猫", "(俗) ねこ"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["The cat sat on the mat."],
    )
    assert result.meanings[0] == "猫"
    assert result.pronunciation.ipa == "/kæt/"
    assert result.examples == ["The cat sat on the mat."]
