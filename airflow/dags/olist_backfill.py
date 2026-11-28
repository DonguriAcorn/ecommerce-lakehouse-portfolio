"""期間(窓)のバックフィル: 取り込み(7表)→ Raw を S3 へ → dbt run → dbt test。

olist_daily の「1日」を「期間」に広げた形。手動で実行し、画面で start_date と end_date を渡す。
一時キーが1時間で切れる(ADR 0012)ので、1回の実行は1時間に収まる大きさの窓にする。
全期間は、窓を分けて何回かに分け、窓の前に毎回 `bash airflow/refresh_credentials.sh` を打つ。
同じ窓を流し直しても結果は変わらない(Raw は上書き、Silver は MERGE)。
"""

from datetime import datetime

# タスクの部品(シェルのコマンドを1つ実行する)と、DAG、画面の入力欄
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

# プロジェクトの Python と dbt(Airflow 本体とは別の venv。イメージの中にある)と、コードの場所
PY = "/opt/project-venv/bin/python"
DBT = "/opt/project-venv/bin/dbt"
PROJECT = "/opt/project"
# 取り込む7表(ingestion/schema.py の registry の名前と同じ綴り。olist_daily と同じ)
TABLES = [
    "orders_events",
    "order_items",
    "reviews",
    "customers",
    "sellers",
    "products",
    "product_category_name_translation",
]
# dbt に、窓(最初の日と最後の日)を渡す。{{ params.xxx }} は実行時に日付へ置き換わる
# --target は画面の env(dev / prod)。target 名が Gold の置き場(ecom_<env>_gold)も決める
DBT_ARGS = (
    "--project-dir dbt --profiles-dir dbt --target {{ params.env }} "
    '--vars \'{start_date: "{{ params.start_date }}", end_date: "{{ params.end_date }}"}\''
)
# 日付の形(YYYY-MM-DD だけ許す)
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
# prod のときだけ、バケット名を prod のものに差し替える(dev は何もしない)。
# export はそのタスクの中だけで有効。LAKE_BUCKET_PROD は compose が .env から渡す
BUCKET_PREFIX = '{% if params.env == "prod" %}export LAKE_BUCKET="$LAKE_BUCKET_PROD"; {% endif %}'


# dbt を流す共通の形(olist_daily と同じ)。dbt の終了コードを保存し、失敗の要約を出してから、
# 保存した終了コードで終わる(失敗ならタスクも失敗になる)
def dbt_with_summary(command: str) -> str:
    return (
        BUCKET_PREFIX +
        # 前回の run_results.json を消す(古い結果を読まないため)
        f"cd {PROJECT} && rm -f dbt/target/run_results.json && "
        f"{DBT} {command} {DBT_ARGS}; status=$?; "
        f"{PY} -m ingestion.dbt_failures dbt/target/run_results.json; "
        "exit $status"
    )


with DAG(
    dag_id="olist_backfill",
    schedule=None,  # 手動のみ
    start_date=datetime(2016, 9, 4),
    catchup=False,  # 過去の分をまとめて追いかけない
    # 画面で入れる窓(既定は最初の30日。最後の日も含む)
    params={
        "start_date": Param("2016-09-04", type="string", pattern=DATE_PATTERN),
        "end_date": Param("2016-10-03", type="string", pattern=DATE_PATTERN),
        # 書き込み先の環境。既定は dev(渡し忘れで prod に書く事故を防ぐ)
        "env": Param("dev", type="string", enum=["dev", "prod"]),
    },
    tags=["olist", "backfill"],
    # リトライは0。期限切れ(認証エラー)は、待ってやり直しても直らず、手元で発行し直すしかないため
    default_args={"retries": 0},
) as dag:
    # 7表の取り込み。窓まるごとを1回で流す(互いに関係がないので同時)。AWS には触れない
    ingest_tasks = [
        BashOperator(
            task_id=f"ingest_{table}",
            bash_command=(
                f"cd {PROJECT} && {PY} -m ingestion.run_ingest --table {table} "
                "--start {{ params.start_date }} --end {{ params.end_date }}"
            ),
        )
        for table in TABLES
    ]

    # 窓の Raw を S3 へ上げる。ここから ingest ロール(AWS_PROFILE は credentials の見出しと同じ)
    upload_raw = BashOperator(
        task_id="upload_raw",
        bash_command=(
            BUCKET_PREFIX + f"cd {PROJECT} && {PY} -m ingestion.upload_raw "
            "--start {{ params.start_date }} --end {{ params.end_date }}"
        ),
        env={"AWS_PROFILE": "ecom-{{ params.env }}-ingest"},
        append_env=True,
    )

    # 取り込みログと隔離ファイル(UTC の今日の run_date)を S3 の logs/ と quarantine/ へ
    # 取り込みが失敗しても動かす
    upload_logs = BashOperator(
        task_id="upload_logs",
        bash_command=BUCKET_PREFIX + f"cd {PROJECT} && {PY} -m ingestion.upload_logs",
        env={"AWS_PROFILE": "ecom-{{ params.env }}-ingest"},
        append_env=True,
        trigger_rule="all_done",
    )

    # Silver を作る(窓ぜんたいで1回)
    dbt_run = BashOperator(task_id="dbt_run", bash_command=dbt_with_summary("run"))

    # テストを流す(同じ窓)
    # silver_freshness(今日の分が届いたか)は、毎日の運用(olist_daily)用なので除外する。
    # 過去の窓では、届く注文が少ない日や、order_items / reviews が届かない期間があり、誤って失敗する
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=dbt_with_summary("test --exclude silver_freshness"),
    )

    # 順番: 7表の取り込み(同時)→ S3 へ → dbt run → dbt test。ログの upload は別枝
    ingest_tasks >> upload_raw >> dbt_run >> dbt_test
    ingest_tasks >> upload_logs
