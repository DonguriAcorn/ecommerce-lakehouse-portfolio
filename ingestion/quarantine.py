"""取り込みを止めるときの例外と、隔離する行の書き出し(どのテーブルの取り込みでも使う)。"""

from pathlib import Path

import pandas as pd

# 隔離した行がこの割合を超えたら、元データの大きな異常とみなして止める
QUARANTINE_LIMIT = 0.01


class IngestStop(Exception):
    """実行全体を止めるときの例外。ログは、投げる前に書いておく。"""


def write_quarantine(
    bad: pd.DataFrame, quarantine_dir: Path, batch_id: str, table: str
) -> Path | None:
    """隔離する行を Parquet に書く。0件なら、ファイルを作らない。

    table は、フォルダ名とファイル名に使う(例: orders_events)。
    """
    # 隔離する行がなければ、空のファイルを作らず、置き場所なし(None)を返す
    if bad.empty:
        return None

    # 実行した日(UTC)。フォルダ名に使う
    run_date = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    # 置き場所は、実行日と batch_id ごとのフォルダ(Raw と同じ、パーティション風の形)
    out_path = (
        quarantine_dir
        / "olist"
        / table
        / f"run_date={run_date}"
        / f"batch_id={batch_id}"
        / f"{table}.parquet"
    )

    # 隔離は「届いたまま」を残す場所なので、値はすべて文字列にそろえる
    # (順位の列に文字が混ざった行などでも、Parquet に書けるようにするため)
    # どの実行で、いつ隔離したかが分かるよう、2つの列を足す(UTC、タイムゾーンの印なし)
    table_df = bad.astype("string").assign(
        _batch_id=batch_id,
        _quarantined_at=pd.Timestamp.now(tz="UTC").tz_localize(None),
    )

    # フォルダがなければ作ってから、Parquet で書く(index=False: 行番号の列は書かない)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table_df.to_parquet(out_path, index=False)
    return out_path
