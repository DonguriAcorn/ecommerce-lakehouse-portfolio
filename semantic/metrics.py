"""セマンティックレイヤー Lv2 の読み込み関数(handoff §9)。

semantic/metrics.yml の指標の定義を読み、DuckDB の SQL を組み立てて、
app/data/ の Parquet から数字を出す。ダッシュボードと AI アナリストは、この関数だけを通す。

使い方:
    from semantic.metrics import query_metric
    query_metric("aov", grain="year")                          # 年ごとの平均注文額
    query_metric("gmv", by=["category_name"], where={"year": "2017"})
"""

from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd
import yaml

# リポジトリの直下(このファイルの1つ上のフォルダ)。data_dir はここからの相対パス
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITIONS = REPO_ROOT / "semantic" / "metrics.yml"

# 時間の細かさごとの、結果の列の名前
TIME_COLUMNS = {"month": "year_month", "quarter": "quarter", "year": "year"}
# 時間で分けず、期間全体で1つの値にする細かさ(KPI のカード用)。
# 月の表を全部足し上げるので、rollup: true の指標だけが使える
ALL = "all"


@lru_cache
def load_definitions(path: Path = DEFAULT_DEFINITIONS) -> dict:
    """metrics.yml を読む。同じファイルは2回目から読み直さない(画面の再描画で毎回読まない)。"""
    with open(path, encoding="utf-8") as f:
        defs = yaml.safe_load(f)  # safe_load: YAML の中のプログラムは実行しない
    validate_definitions(defs)  # 書き間違いは、読み込んだ時点で止める
    return defs


def validate_definitions(defs: dict) -> None:
    """定義の中の食い違い(ない表、ない切り口、ない時間の細かさ)を見つけたら止める。"""
    tables = defs["tables"]
    for table_name, table in tables.items():
        # 表の時間の細かさは、決めた3つのどれか
        if table["grain"] not in defs["time_grains"]:
            raise ValueError(f"表 {table_name} の grain が不明: {table['grain']}")
        # 表の切り口は、dimensions のブロックにあるもの
        for dim in table["dimensions"]:
            if dim not in defs["dimensions"]:
                raise ValueError(f"表 {table_name} の切り口 {dim} が dimensions にない")
    names = set()
    for metric in defs["metrics"]:
        # 名前の重複は、どちらを使うか決まらないので止める
        if metric["name"] in names:
            raise ValueError(f"指標の名前が重複: {metric['name']}")
        names.add(metric["name"])
        # 材料の表は、tables のブロックにあるもの
        for source in metric["sources"]:
            if source not in tables:
                raise ValueError(f"指標 {metric['name']} の表 {source} が tables にない")
        # rollup は true / false のどちらか(書き忘れで足し上げてしまう事故を防ぐ)
        if not isinstance(metric.get("rollup"), bool):
            raise ValueError(f"指標 {metric['name']} の rollup は true か false で書く")


def get_metric(name: str, defs: dict | None = None) -> dict:
    """指標の定義を1件返す(画面の見出し label や説明 description に使う)。"""
    defs = defs or load_definitions()
    for metric in defs["metrics"]:
        if metric["name"] == name:
            return metric
    known = ", ".join(m["name"] for m in defs["metrics"])
    raise ValueError(f"指標 {name} は定義にない(あるのは: {known})")


def time_expr(table: dict, grain: str) -> str:
    """表の時間の列から、求める細かさの時間を作る SQL の式を返す。作れなければ止める。"""
    col = table["time_column"]
    if table["grain"] == "year":
        # 年の表からは年しか作れない(月や四半期には分けられない)
        if grain != "year":
            raise ValueError(f"年の表から {grain} は作れない")
        return col
    # ここから下は月の表(year_month = 'YYYY-MM')
    if grain == "month":
        return col
    if grain == "year":
        return f"substr({col}, 1, 4)"  # '2017-11' → '2017'
    if grain == "quarter":
        # '2017-11' → '2017-Q4'(月を 1〜3 → Q1 のように3か月ずつまとめる)
        quarter_no = f"(cast(substr({col}, 6, 2) as integer) + 2) // 3"  # 11月 → (11+2)//3 = 4
        return f"substr({col}, 1, 4) || '-Q' || cast({quarter_no} as varchar)"
    raise ValueError(f"時間の細かさが不明: {grain}")


def choose_table(metric: dict, grain: str, by: list[str], defs: dict) -> str:
    """sources を上から見て、求める細かさと切り口を満たす最初の表の名前を返す。"""
    for source in metric["sources"]:
        table = defs["tables"][source]
        # 切り口の列が、全部この表にあるか
        if not set(by) <= set(table["dimensions"]):
            continue
        # 期間全体の値は、足し上げてよい指標なら、どの表からでも出せる
        if grain == ALL:
            if metric["rollup"]:
                return source
            continue
        # 表の細かさがちょうど同じなら使える
        if table["grain"] == grain:
            return source
        # 月の表を足し上げて四半期・年にするのは、rollup: true の指標だけ
        if metric["rollup"] and table["grain"] == "month" and grain in ("quarter", "year"):
            return source
    raise ValueError(
        f"指標 {metric['name']} は、細かさ {grain}・切り口 {by} では出せない"
        f"(使える表: {metric['sources']}、rollup: {metric['rollup']})"
    )


def build_sql(
    name: str,
    grain: str = "month",
    by: list[str] | None = None,
    where: dict | None = None,
    defs: dict | None = None,
    data_dir: Path | None = None,
) -> tuple[str, list]:
    """指標の SQL と、絞り込みの値(? に入る値の並び)を返す。実行はしない(テストで中身を見る)。"""
    defs = defs or load_definitions()
    by = by or []
    where = where or {}
    if grain not in [*defs["time_grains"], ALL]:
        raise ValueError(f"時間の細かさは {[*defs['time_grains'], ALL]} のどれか: {grain}")

    metric = get_metric(name, defs)
    table_name = choose_table(metric, grain, by, defs)
    table = defs["tables"][table_name]
    data_dir = data_dir or (REPO_ROOT / defs["data_dir"])
    path = str(data_dir / f"{table_name}.parquet").replace("'", "''")  # パスの ' を SQL 用に重ねる

    # 絞り込みに使える列: 表の切り口と、この表から作れる時間の列
    filterable = {dim: dim for dim in table["dimensions"]}
    for g, out_col in TIME_COLUMNS.items():
        try:
            filterable[out_col] = time_expr(table, g)
        except ValueError:
            pass  # 年の表の year_month のように、作れない時間の列は絞り込みに使えない

    conditions, params = [], []
    for col, value in where.items():
        # 列名は、決まった一覧にあるものだけ(SQL に文字をそのまま入れないため)
        if col not in filterable:
            raise ValueError(f"{col} では絞り込めない(使える列: {sorted(filterable)})")
        # 1つの値でも、並び(list / tuple。画面の複数選択)でも受け取る
        values = list(value) if isinstance(value, (list, tuple)) else [value]
        if not values:
            raise ValueError(f"{col} の絞り込みの値が空")  # in () は SQL の書き間違いになるため
        # 値は ? の場所に DuckDB が安全に入れる(SQL の文字に混ぜない)
        conditions.append(f"{filterable[col]} in ({', '.join('?' for _ in values)})")
        params.extend(values)

    # 結果の列: 時間(all のときはなし)、切り口、指標の順
    if grain == ALL:
        select_cols, group_cols = [*by], [*by]
    else:
        time_col = TIME_COLUMNS[grain]
        select_cols = [f"{time_expr(table, grain)} as {time_col}", *by]
        group_cols = [time_col, *by]
    # 計算式は metrics.yml のもの。結果は小数(double)にそろえる
    select_cols.append(f"cast(({metric['expression']}) as double) as {metric['name']}")
    sql = (
        f"select {', '.join(select_cols)}\n"
        f"from read_parquet('{path}')\n"
        + (f"where {' and '.join(conditions)}\n" if conditions else "")
        # まとめる列がないとき(期間全体・切り口なし)は、全体で1行になる
        + (f"group by {', '.join(group_cols)}\norder by {', '.join(group_cols)}"
           if group_cols else "")
    )
    return sql, params


def query_metric(
    name: str,
    grain: str = "month",
    by: list[str] | None = None,
    where: dict | None = None,
    defs: dict | None = None,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """指標を計算して、表(DataFrame)で返す。列は「時間、切り口…、指標」の順。"""
    sql, params = build_sql(name, grain, by, where, defs, data_dir)
    with duckdb.connect() as con:  # メモリの中だけの DuckDB。Parquet を直接読む
        return con.execute(sql, params).df()


# ---- 期間比較(前の期間比、前年同期比) ----

# 1年に何期あるか(前年同期 = この数だけ前の期間)
PERIODS_PER_YEAR = {"month": 12, "quarter": 4, "year": 1}


def shift_period(key: str, grain: str, n: int) -> str:
    """期間の値を n 期前にずらす。例: ('2017-01', month, 1) → '2016-12'。

    行の位置でずらさないのは、データに抜けた月があるため(2016-11 は注文が0件で行がない)。
    """
    if grain == "month":
        y, m = int(key[:4]), int(key[5:7])
        idx = y * 12 + (m - 1) - n  # 月を通し番号にしてから引く(年をまたいでも正しい)
        return f"{idx // 12}-{idx % 12 + 1:02d}"
    if grain == "quarter":
        y, q = int(key[:4]), int(key[-1])
        idx = y * 4 + (q - 1) - n
        return f"{idx // 4}-Q{idx % 4 + 1}"
    if grain == "year":
        return str(int(key) - n)
    raise ValueError(f"期間比較は month / quarter / year だけ: {grain}")


def query_metric_changes(
    name: str,
    grain: str = "month",
    by: list[str] | None = None,
    where: dict | None = None,
    defs: dict | None = None,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """指標に、前の期間と前年同期の値と変化を足した表を返す。

    列: 時間、切り口…、指標、prev_period(前の期間の値)、prev_year(前年同期の値)、
        change_prev_period、change_prev_year(変化)
    変化の出し方は単位で変える: 割合(unit: ratio)は差(0.05 → 0.06 で +0.01 = +1 ポイント)、
    それ以外は伸び率(100 → 120 で +0.2 = +20%)。前の値がないか 0 なら空。
    """
    defs = defs or load_definitions()
    by = by or []
    where = where or {}
    # 時間で絞ると前の期間が消えてしまうので、時間の絞り込みは受け付けない(呼ぶ側で後から絞る)
    time_keys = set(TIME_COLUMNS.values()) & set(where)
    if time_keys:
        raise ValueError(f"期間比較では時間で絞り込めない(結果を後で絞る): {sorted(time_keys)}")

    current = query_metric(name, grain, by, where, defs, data_dir)
    time_col = TIME_COLUMNS[grain]
    keys = [time_col, *by]

    def previous(n: int, col: str) -> pd.DataFrame:
        """n 期前の値を、今の期間の行に並べられる形にする(期間をずらした写し)。"""
        prev = current[[*keys, name]].copy()
        # 例: 2016-12 の行を「2017-01 から見た前月」にするため、期間を n 期あとにずらす
        prev[time_col] = prev[time_col].map(lambda k: shift_period(k, grain, -n))
        return prev.rename(columns={name: col})

    # 期間の値で突き合わせる(前の期間の行がなければ空になる)
    out = current.merge(previous(1, "prev_period"), on=keys, how="left")
    out = out.merge(previous(PERIODS_PER_YEAR[grain], "prev_year"), on=keys, how="left")

    is_ratio = get_metric(name, defs)["unit"] == "ratio"
    for prev_col, change_col in [("prev_period", "change_prev_period"),
                                 ("prev_year", "change_prev_year")]:
        if is_ratio:
            out[change_col] = out[name] - out[prev_col]  # 割合は差(ポイント)
        else:
            prev = out[prev_col].where(out[prev_col] != 0)  # 0 は空にする(0 で割らない)
            out[change_col] = out[name] / prev - 1  # それ以外は伸び率
    return out
