"""ローカルのログのうち、最終更新から N 日(既定 90)を過ぎたファイルを消す。

既定は「一覧を出すだけ」で、--delete を付けたときだけ消す(誤って消さないため)。
対象は airflow/logs/ と data/logs/。dbt/logs/ の dbt.log は追記され続けて
最終更新が毎回新しくなるので、対象に入れない。
"""

import argparse
import time
from pathlib import Path

# 既定の掃除の対象(プロジェクト直下から見た場所)
DEFAULT_DIRS = ["airflow/logs", "data/logs"]
# 残す日数(2026-11-14 の決め事: ローカルのログは 90 日)
DEFAULT_DAYS = 90


def find_old_files(dirs: list[Path], days: int, now: float) -> list[Path]:
    """最終更新が days 日より前のファイルを、名前順で返す。"""
    # この時刻(秒)より前に更新されたものが、古いファイル
    cutoff = now - days * 86400
    old = []
    for d in dirs:
        # 場所がなければ何もしない(まだ一度も動かしていない環境のため)
        if not d.exists():
            continue
        for f in d.rglob("*"):
            # シンボリックリンク(例: dag_processor/latest)は触らない
            if f.is_file() and not f.is_symlink() and f.stat().st_mtime < cutoff:
                old.append(f)
    return sorted(old)


def remove_empty_dirs(dirs: list[Path]) -> int:
    """空になったフォルダを消す(掃除の対象の場所そのものは残す)。消した数を返す。"""
    removed = 0
    for d in dirs:
        if not d.exists():
            continue
        # 深い順に見る(子が消えてから親を調べるため)
        for sub in sorted((p for p in d.rglob("*") if p.is_dir()), reverse=True):
            # シンボリックリンクは触らない。中身がなければ消す
            if not sub.is_symlink() and not any(sub.iterdir()):
                sub.rmdir()
                removed += 1
    return removed


def main() -> int:
    """実行の流れ: 引数 → 古いファイルを探す → 一覧(既定)または削除(--delete)。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="残す日数")
    parser.add_argument("--delete", action="store_true", help="付けたときだけ実際に消す")
    parser.add_argument("dirs", nargs="*", default=DEFAULT_DIRS, help="掃除する場所")
    args = parser.parse_args()

    dirs = [Path(d) for d in args.dirs]
    old = find_old_files(dirs, args.days, time.time())
    for f in old:
        print(f)

    if not args.delete:
        print(f"{len(old)} ファイルが {args.days} 日より古い(消すには --delete を付ける)")
        return 0

    # 実際に消す
    for f in old:
        f.unlink()
    removed = remove_empty_dirs(dirs)
    print(f"{len(old)} ファイルと、空のフォルダ {removed} 個を消しました")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
