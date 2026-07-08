from yak.models import DictionaryResult, Pronunciation
from yak.render import oneline_text, render_dictionary


def test_render_dictionary_full() -> None:
    result = DictionaryResult(
        meanings=["猫", "(俗) ねこ、キャット"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["The cat sat on the mat.", "I have a cat."],
    )
    expected = """\
意味:
1. 猫
2. (俗) ねこ、キャット

発音:
キャット / /kæt/

例文:
- The cat sat on the mat.
- I have a cat."""
    assert render_dictionary(result) == expected


def test_render_dictionary_single_items() -> None:
    result = DictionaryResult(
        meanings=["cat"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["I have a cat."],
    )
    text = render_dictionary(result)
    assert "1. cat" in text
    assert "- I have a cat." in text


def test_render_dictionary_oneline_first_meaning() -> None:
    result = DictionaryResult(
        meanings=["猫", "ネコ科の動物"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["I have a cat."],
    )
    assert render_dictionary(result, oneline=True) == "猫"


def test_render_dictionary_oneline_empty_meanings() -> None:
    result = DictionaryResult(
        meanings=[],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=[],
    )
    assert render_dictionary(result, oneline=True) == ""


def test_oneline_text_joins_newlines() -> None:
    assert (
        oneline_text("今日はいい天気です。\n\n散歩に行きましょう。")
        == "今日はいい天気です。 散歩に行きましょう。"
    )


def test_oneline_text_strips_surrounding_whitespace() -> None:
    assert oneline_text("  hello \n world \n") == "hello world"
