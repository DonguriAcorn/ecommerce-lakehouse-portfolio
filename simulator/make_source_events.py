"""Olist の CSV から、業務システムが毎日届けるファイル(ソース)を、表ごとに1回だけ作る。

作ったファイルは data/source/<表の名前>/ に置く(Git の管理外)。
パイプライン(ingestion/run_ingest.py)は、このファイルを「届いたもの」として読むだけで、
中身を作らない(ADR 0010、ADR 0011)。
ファイルの形(列と日時の書式)は、受け取り側が決めた ingestion/schema.py の registry に合わせる。
orders は出来事に分けてから届け、ほかの表は行ごとに届く日を付けて届ける。
"""

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from ingestion.schema import (
    ORDERS_EVENTS,
    REGISTRY,
    TIMESTAMP,
    TIMESTAMP_FORMAT,
    TableSpec,
    expected_days,
)
from simulator.orders_events import build_event_records, load_orders
from simulator.table_sources import build_table_records

# 入力(元の CSV)と、出力(ソース)の置き場所。どちらも Git の管理外
OLIST_DIR = Path("data/olist")
SOURCE_ROOT = Path("data/source")  # この下に <表の名前>/ を作る

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


def write_source_events(
    records: pd.DataFrame,
    source_dir: Path,
    spec: TableSpec = ORDERS_EVENTS,
    days: pd.DatetimeIndex | None = None,
) -> int:
    """届いた日ごとに、JSON Lines のファイルを書く。行のない日も、空のファイルを書く。

    days を省くと、最初に届く日から最後に届く日まで(orders の書き方)。
    業務システムは届くはずの日に必ずファイルを届ける想定。届かない日は、取り込み側で止める。
    書いたファイルの数を返す。
    """
    if days is None:
        days = pd.date_range(records["arrival_date"].min(), records["arrival_date"].max(), freq="D")
    for day in days:
        # その日に届く行。JSON には registry の列だけを書く(arrival_date などは書かない)
        day_records = records.loc[records["arrival_date"] == day, list(spec.columns)].copy()
        # 日時型の列は、決めた書式の文字列にする(空の日時は null になる)。
        # CSV から文字列のまま読んだ表は、そのまま書く
        for column in spec.columns_of(TIMESTAMP):
            if pd.api.types.is_datetime64_any_dtype(day_records[column]):
                day_records[column] = day_records[column].dt.strftime(TIMESTAMP_FORMAT)

        # 置き場所は、届いた日ごとのフォルダ
        # (例: arrival_date=2017-10-04/order_items_20171004.jsonl)
        out_path = (
            source_dir / f"arrival_date={day:%Y-%m-%d}" / f"{spec.name}_{day:%Y%m%d}.jsonl"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if day_records.empty:
            # 行のない日は、中身が空のファイル
            out_path.write_text("", encoding="utf-8")
        else:
            # 1行 = 1件の JSON。force_ascii=False: 文字を \uXXXX にしない
            day_records.to_json(out_path, orient="records", lines=True, force_ascii=False)
    return len(days)


def main() -> int:
    """表を選び、CSV から届く日を付けた表を作って、ソースのファイルを書く。成功は 0。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table", default="orders_events", choices=list(REGISTRY), help="作る表"
    )
    parser.add_argument("--out", type=Path, default=None, help="書き出すフォルダ")
    parser.add_argument(
        "--late-share", type=float, default=0.0, help="遅れて届く出来事の割合(0〜1。orders だけ)"
    )
    parser.add_argument("--late-days", type=int, default=3, help="遅れる日数(orders だけ)")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="遅延の対象を決める seed")
    args = parser.parse_args()

    spec = REGISTRY[args.table]
    out = args.out or SOURCE_ROOT / spec.name

    # 前に作ったファイルが残ると、同じ行が2つの日に入る恐れがある。中身があれば、消さずに止める
    if out.exists() and any(out.iterdir()):
        print(f"{out} にファイルがあります。中身を確かめてから消し、やり直してください")
        return 1

    if spec is ORDERS_EVENTS:
        # orders: CSV を読み、出来事の表を作り、届いた日を付ける(元データは隔離 0 件と確認済み)
        orders = load_orders(OLIST_DIR / spec.source_csv)
        records = assign_arrival_dates(
            build_event_records(orders), args.late_share, args.late_days, args.seed
        )
        files = write_source_events(records, out)
        late = int((records["arrival_date"] != records["event_date"]).sum())
        print(f"出来事 {len(records)} 件(遅延 {late} 件)/ ファイル {files} 個 -> {out}")
        return 0

    # ほかの表: 遅延は入れない(子の表は親と同じ日か後に届く約束を守るため)
    if args.late_share > 0:
        print("遅延(--late-share)は orders だけで使えます")
        return 1
    records = build_table_records(spec, OLIST_DIR)
    days = expected_days(spec)
    # 届くはずの日の外に届く行があれば、書かずに止める(ファイルから行が漏れるのを防ぐ)
    outside = ~records["arrival_date"].isin(days)
    if outside.any():
        print(f"期間の外に届く行が {int(outside.sum())} 件あります。registry の期間を確かめます")
        return 1
    files = write_source_events(records, out, spec, days)
    print(f"{spec.name}: {len(records)} 行 / ファイル {files} 個 -> {out}")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす
if __name__ == "__main__":
    raise SystemExit(main())
