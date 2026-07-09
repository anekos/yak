import stat
from pathlib import Path

import pytest

from yak.history import HISTORY_LIMIT, history_file, readline_history

readline = pytest.importorskip("readline")


@pytest.fixture(autouse=True)
def _clear_readline_history() -> None:
    """readline の履歴はプロセス全体で共有されるので、各テストの前に空にする。"""
    readline.clear_history()


def test_history_file_is_named_history() -> None:
    assert history_file().name == "history"


def test_history_is_written_on_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """履歴ファイルの中身は readline の実装 (GNU / libedit) 依存なので、行の存在だけ見る。"""
    path = tmp_path / "state" / "history"
    monkeypatch.setattr("yak.history.history_file", lambda: path)
    with readline_history():
        readline.add_history("hello")
    assert "hello" in path.read_text().splitlines()


def test_history_survives_a_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "history"
    monkeypatch.setattr("yak.history.history_file", lambda: path)
    with readline_history():
        readline.add_history("cat")
    readline.clear_history()
    with readline_history():
        assert readline.get_history_item(1) == "cat"


def test_history_length_is_limited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "history"
    monkeypatch.setattr("yak.history.history_file", lambda: path)
    with readline_history():
        assert readline.get_history_length() == HISTORY_LIMIT


def test_history_file_is_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "history"
    monkeypatch.setattr("yak.history.history_file", lambda: path)
    with readline_history():
        readline.add_history("secret")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_history_file_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("yak.history.history_file", lambda: tmp_path / "absent")
    with readline_history():
        pass


def test_unwritable_history_file_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    unwritable = tmp_path / "ro"
    unwritable.mkdir(mode=0o500)
    monkeypatch.setattr("yak.history.history_file", lambda: unwritable / "history")
    with readline_history():
        readline.add_history("hello")
