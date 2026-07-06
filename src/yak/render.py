from yak.models import DictionaryResult


def render_dictionary(result: DictionaryResult) -> str:
    lines = ["意味:"]
    lines.extend(f"{i}. {meaning}" for i, meaning in enumerate(result.meanings, 1))
    lines.append("")
    lines.append("発音:")
    lines.append(f"{result.pronunciation.katakana} / {result.pronunciation.ipa}")
    lines.append("")
    lines.append("例文:")
    lines.extend(f"- {example}" for example in result.examples)
    return "\n".join(lines)
