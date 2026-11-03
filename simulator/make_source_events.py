"""Olist の CSV から、業務システムが毎日届けるイベントのファイル(ソース)を、1回だけ作る。

作ったファイルは data/source/ に置く(Git の管理外)。パイプライン(ingestion/run_ingest.py)は、
このファイルを「届いたもの」として読むだけで、イベントを作らない(ADR 0010)。
ファイルの形(列と日時の書式)は、受け取り側が決めた ingestion/schema.py に合わせる。
"""

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from ingestion.schema import EVENT_COLUMNS, SOURCE_TIMESTAMP_COLUMNS, TIMESTAMP_FORMAT
from simulator.orders_events import build_event_records, load_orders

# 入力(元の CSV)と、出力(ソース)の置き場所。どちらも Git の管理外
ORDERS_CSV = Path("data/olist/olist_orders_dataset.csv")
SOURCE_DIR = Path("data/source/orders_events")

# 遅延の対象を決める既定の seed(文字列)。変えると、遅延する出来事が入れ替わる
DEFAULT_SEED = "olist-late-v1"


def pick_late_events(records: pd.DataFrame, share: float, seed: str) -> pd.Series:
    """遅れて届く出来事を、(order_id, event_type) と seed から決めて、True の印で返す。

    Python の hash() は実行ごとに値が変わるので使わず、sha256 を使う(何度作っても同じになる)。
    """
    # 「seed|注文ID|種類」の文字を sha256 にかけ、先頭8桁(16進)を 0〜1 の数に直す
    keys = seed + "|" + records["order_id"] + "|" + records["event_type"]
    fraction = keys.map(
        lambda key: int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    )
    # その数が share より小さい出来事を、遅延の対象にする(share=0.05 なら、およそ 5%)
    return fraction < share


def assign_arrival_dates(
    records: pd.DataFrame, share: float, late_days: int, seed: str
) -> pd.DataFrame:
    """出来事ごとに、届いた日(arrival_date)を付ける。ふつうは起きた日、遅延の対象だけ後ろへずらす。"""
    # 元の表を書き換えないよう、複製してから列を足す
    records = records.copy()
    is_late = pick_late_events(records, share, seed)
    # 届いた日 = 起きた日 + (遅延の対象なら late_days 日、そうでなければ 0 日)
    records["arrival_date"] = records["event_date"] + pd.to_timedelta(
        is_late.astype(int) * late_days, unit="D"
    )
    return records


def write_source_events(records: pd.DataFrame, source_dir: Path) -> int:
    """届いた日ごとに、JSON Lines のファイルを書く。出来事のない日も、空のファイルを書く。

    業務システムは毎日ファイルを届ける想定。届かない日は、取り込み側で「ソースがない」として止める。
    書いたファイルの数を返す。
    """
    # 最初の日から最後の日まで、1日ずつ
    days = pd.date_range(records["arrival_date"].min(), records["arrival_date"].max(), freq="D")
    for day in days:
        # その日に届く出来事。JSON には、決めた列だけを書く(event_date と arrival_date は書かない)
        day_records = records.loc[records["arrival_date"] == day, EVENT_COLUMNS].copy()
        # 日時は文字列にする(空の日時は null になる)
        for column in SOURCE_TIMESTAMP_COLUMNS:
            day_records[column] = day_records[column].dt.strftime(TIMESTAMP_FORMAT)

        # 置き場所は、届いた日ごとのフォルダ
        # (例: arrival_date=2017-10-04/orders_events_20171004.jsonl)
        out_path = (
            source_dir / f"arrival_date={day:%Y-%m-%d}" / f"orders_events_{day:%Y%m%d}.jsonl"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if day_records.empty:
            # 出来事のない日は、中身が空のファイル
            out_path.write_text("", encoding="utf-8")
        else:
            # 1行 = 1件の JSON。force_ascii=False: 文字を \uXXXX にしない
            day_records.to_json(out_path, orient="records", lines=True, force_ascii=False)
    return len(days)


def main() -> int:
    """CSV を読み、出来事の表を作り、届いた日を付けて、ソースのファイルを書く。成功は 0。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=SOURCE_DIR, help="書き出すフォルダ")
    parser.add_argument(
        "--late-share", type=float, default=0.0, help="遅れて届く出来事の割合(0〜1)"
    )
    parser.add_argument("--late-days", type=int, default=3, help="遅れる日数")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="遅延の対象を決める seed")
    args = parser.parse_args()

    # 前に作ったファイルが残ると、同じ出来事が2つの日に入る恐れがある。中身があれば、消さずに止める
    if args.out.exists() and any(args.out.iterdir()):
        print(f"{args.out} にファイルがあります。中身を確かめてから消し、やり直してください")
        return 1

    # CSV を読み(元データは隔離 0 件と確認済み)、出来事の表を作り、届いた日を付ける
    orders = load_orders(ORDERS_CSV)
    records = assign_arrival_dates(
        build_event_records(orders), args.late_share, args.late_days, args.seed
    )
    files = write_source_events(records, args.out)

    # 結果のまとめ: 出来事の数、遅れて届く数、書いたファイルの数
    late = int((records["arrival_date"] != records["event_date"]).sum())
    print(f"出来事 {len(records)} 件(遅延 {late} 件)/ ファイル {files} 個 -> {args.out}")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす
if __name__ == "__main__":
    raise SystemExit(main())
