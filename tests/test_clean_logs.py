"""clean_logs のテスト。一時フォルダで、古いファイルだけが対象になることを確かめる。"""

import os
import time
from pathlib import Path

from ingestion.clean_logs import find_old_files, remove_empty_dirs

DAY = 86400


def _make(path: Path, age_days: int) -> Path:
    # ファイルを作り、最終更新を age_days 日前にする
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    t = time.time() - age_days * DAY
    os.utime(path, (t, t))
    return path


def test_find_old_files_picks_only_older_than_days(tmp_path):
    old = _make(tmp_path / "run_date=2026-01-01" / "a.log", 100)
    _make(tmp_path / "run_date=2026-11-01" / "b.log", 10)
    # 90 日より古い 1 つだけが返る(10 日前のものは返らない)
    assert find_old_files([tmp_path], 90, time.time()) == [old]


def test_find_old_files_ignores_missing_dir(tmp_path):
    # 存在しない場所があっても、エラーにならず空になる
    assert find_old_files([tmp_path / "none"], 90, time.time()) == []


def test_find_old_files_skips_symlinks(tmp_path):
    target = _make(tmp_path / "real" / "a.log", 100)
    link = tmp_path / "latest"
    link.symlink_to(target)
    # 実体だけが返り、リンクは返らない
    assert find_old_files([tmp_path], 90, time.time()) == [target]


def test_remove_empty_dirs_keeps_root_and_nonempty(tmp_path):
    # 古いファイルを消したあとの空フォルダだけが消え、中身のあるフォルダとルートは残る
    (tmp_path / "empty" / "deeper").mkdir(parents=True)
    keep = _make(tmp_path / "keep" / "b.log", 1)
    assert remove_empty_dirs([tmp_path]) == 2
    assert tmp_path.exists() and keep.exists()
    assert not (tmp_path / "empty").exists()
