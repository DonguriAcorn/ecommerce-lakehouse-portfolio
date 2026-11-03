"""orders の元データを検証し、停止と隔離を判定する。"""

from pathlib import Path

import pandas as pd

from ingestion.replay_orders import TIMESTAMP_COLUMNS
from ingestion.run_log import RunLog

# ログに入れる、処理の段階の名前
STAGE_LOAD = "ORDERS_LOAD"  # CSV を読む段階
STAGE_VALIDATE = "ORDERS_VALIDATE"  # 行を検証する段階

# 元の CSV に必ず要る8列(order_id などの3列 + 日時の5列)
REQUIRED_COLUMNS = ["order_id", "customer_id", "order_status", *TIMESTAMP_COLUMNS]

# 既知の order_status(orders-data-profile.md)。これ以外は隔離する
KNOWN_STATUSES = [
    "created",
    "approved",
    "invoiced",
    "processing",
    "shipped",
    "delivered",
    "canceled",
    "unavailable",
]

# 隔離した行がこの割合を超えたら、元データの大きな異常とみなして止める
QUARANTINE_LIMIT = 0.01

# 問題の種類(code)ごとの、人が読む文。ログの message に使う
WHAT = {
    "EMPTY_REQUIRED": "必須の列が空の行があります",
    "DUPLICATE_KEY": "order_id が重複している行があります",
    "UNPARSABLE_TIMESTAMP": "日時として読めない値があります",
    "UNKNOWN_STATUS": "既知の8つ以外の order_status があります",
}


class IngestStop(Exception):
    """実行全体を止めるときの例外。ログは、投げる前に書いておく。"""


def read_orders_csv(csv_path: Path, log: RunLog) -> pd.DataFrame:
    """CSV を文字列のまま読み、ファイルと列を確かめる。問題があれば止める。"""
    try:
        # dtype=str: 日時への変換は、検証のあとで行うので、ここでは全部文字列で読む
        raw = pd.read_csv(csv_path, dtype=str)
    except FileNotFoundError:
        # 先にログを書いてから止める(止めたあとでは、理由を書けないため)
        log.write(
            "ERROR",
            STAGE_LOAD,
            "SOURCE_NOT_FOUND",
            f"元の CSV がありません / {csv_path}",
        )
        raise IngestStop("SOURCE_NOT_FOUND") from None
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
        # 壊れた CSV(表の形が崩れている、空、文字コードが違う)
        log.write(
            "ERROR",
            STAGE_LOAD,
            "SOURCE_NOT_FOUND",
            f"元の CSV を読めません / {csv_path}",
        )
        raise IngestStop("SOURCE_NOT_FOUND") from None

    # 必要な8列のうち、CSV にない列を集める
    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        log.write(
            "ERROR",
            STAGE_LOAD,
            "MISSING_COLUMN",
            "必要な列がありません",
            column=", ".join(missing),
            count=len(missing),
        )
        raise IngestStop("MISSING_COLUMN")
    return raw


def validate_orders(
    raw: pd.DataFrame,
    log: RunLog,
    quarantine_limit: float = QUARANTINE_LIMIT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全行を検証し、(良い行, 隔離する行) を返す。隔離が多すぎれば止める。"""
    # (問題の種類, 列名) ごとに、「その問題に当たる行」を True にした列をためる箱
    hits: dict[tuple[str, str], pd.Series] = {}

    # --- 必須の列が空 ---
    # order_id と購入日時は、空だとリプレイが動かない。空欄(NaN)も、空白だけの文字も「空」
    for column in ["order_id", "order_purchase_timestamp"]:
        is_blank = raw[column].isna() | raw[column].str.strip().eq("")
        hits[("EMPTY_REQUIRED", column)] = is_blank

    # --- order_id の重複 ---
    # keep=False: 重複した「すべての行」を True にする(2つ目以降だけにしない)
    # notna(): 空の ID は重複扱いにしない(空は上で隔離する)
    hits[("DUPLICATE_KEY", "order_id")] = raw["order_id"].notna() & raw[
        "order_id"
    ].duplicated(keep=False)

    # --- 日時として読めない値 ---
    for column in TIMESTAMP_COLUMNS:
        # errors="coerce": 読めない値はエラーにせず、NaT(日時の空)にする
        parsed = pd.to_datetime(raw[column], errors="coerce")
        # 「元は値があった」のに「変換したら空になった」行だけが、読めない値。
        # もともと空の行(まだ承認されていない注文など)は正常なので含めない
        hits[("UNPARSABLE_TIMESTAMP", column)] = raw[column].notna() & parsed.isna()

    # --- 既知の8つ以外の状態 ---
    # ~ は「でない」。空の状態も、既知ではないので当たる
    hits[("UNKNOWN_STATUS", "order_status")] = ~raw["order_status"].isin(KNOWN_STATUSES)

    # --- 当たりがあった問題ごとに、ログを1行書く ---
    for (code, column), mask in hits.items():
        if mask.any():
            if code == "EMPTY_REQUIRED":
                samples = []  # 空の値は例にならないので、付けない
            else:
                # 当たった行の値から、空と重複を除き、先頭の3つを例にする
                samples = raw.loc[mask, column].dropna().unique()[:3].tolist()
            log.write(
                "WARNING",
                STAGE_VALIDATE,
                code,
                WHAT[code],
                column=column,
                count=int(mask.sum()),
                samples=samples or None,
            )

    # --- 隔離する行を決める ---
    # すべての問題の列を横に並べ、行ごとに「どれか1つでも当たる」かを調べる
    any_hit = pd.concat(hits.values(), axis=1).any(axis=1)
    bad = raw[any_hit].copy()

    # --- 隔離が多すぎれば止める ---
    # 割り算を避けたのは、行が0件のときに 0 で割らないため
    if len(bad) > len(raw) * quarantine_limit:
        log.write(
            "ERROR",
            STAGE_VALIDATE,
            "QUARANTINE_OVER_LIMIT",
            "隔離する行が上限を超えました",
            count=len(bad),
        )
        raise IngestStop("QUARANTINE_OVER_LIMIT")

    # --- 隔離の理由を、行ごとにまとめる ---
    # 1行に複数の問題があっても、隔離は1回。理由はすべて残す
    codes, columns = [], []
    for index in bad.index:
        # この行が当たった (問題の種類, 列名) の一覧
        found = [key for key, mask in hits.items() if mask.loc[index]]
        # dict.fromkeys: 重複を除き、順番を保つ。カンマでつないで1つの文字にする
        codes.append(",".join(dict.fromkeys(code for code, _ in found)))
        columns.append(",".join(dict.fromkeys(column for _, column in found)))
    bad["_error_codes"] = codes
    bad["_error_columns"] = columns

    # 良い行(隔離に当たらなかった行)と、隔離する行を返す
    return raw[~any_hit].copy(), bad


def write_quarantine(
    bad: pd.DataFrame, quarantine_dir: Path, batch_id: str
) -> Path | None:
    """隔離する行を Parquet に書く。0件なら、ファイルを作らない。"""
    # 隔離する行がなければ、空のファイルを作らず、置き場所なし(None)を返す
    if bad.empty:
        return None

    # 実行した日(UTC)。フォルダ名に使う
    run_date = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    # 置き場所は、実行日と batch_id ごとのフォルダ(Raw と同じ、パーティション風の形)
    out_path = (
        quarantine_dir
        / "olist"
        / "orders"
        / f"run_date={run_date}"
        / f"batch_id={batch_id}"
        / "orders.parquet"
    )

    # どの実行で、いつ隔離したかが分かるよう、2つの列を足す(UTC、タイムゾーンの印なし)
    table = bad.assign(
        _batch_id=batch_id,
        _quarantined_at=pd.Timestamp.now(tz="UTC").tz_localize(None),
    )

    # フォルダがなければ作ってから、Parquet で書く(index=False: 行番号の列は書かない)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)
    return out_path
