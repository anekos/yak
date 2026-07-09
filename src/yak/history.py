from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from platformdirs import user_state_dir

HISTORY_LIMIT = 1000


def history_file() -> Path:
    return Path(user_state_dir("yak")) / "history"


@contextmanager
def readline_history() -> Iterator[None]:
    """対話モードに readline の行編集と永続履歴を与える。

    readline を import するだけで組み込みの input() が行編集
    (Ctrl-P/Ctrl-N の履歴、Ctrl-A、Ctrl-R など)を使うようになる。
    """
    try:
        import readline
    except ImportError:  # Windows の標準 Python には readline がない
        yield
        return

    path = history_file()
    try:
        readline.read_history_file(path)
    except OSError:  # 未作成・読めない・壊れている
        pass
    readline.set_history_length(HISTORY_LIMIT)
    try:
        yield
    finally:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(path)
            # 入力した文章がそのまま残るので、本人だけが読めるようにする。
            path.chmod(0o600)
        except OSError:
            pass
