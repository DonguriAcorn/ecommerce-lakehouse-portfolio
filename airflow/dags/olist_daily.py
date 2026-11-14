"""1日分の流れ: 取り込み(7表)→ Raw を S3 へ → dbt run → dbt test。

手動で実行し、画面で target_date(取り込む日)を渡す。データが 2016〜2018 年のものなので、
今日の日付に合わせたスケジュールは組まない(schedule=None)。
"""

from datetime import datetime, timedelta

# タスクの部品(シェルのコマンドを1つ実行する)と、DAG、画面の入力欄
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

# プロジェクトの Python と dbt(Airflow 本体とは別の venv。イメージの中にある)と、コードの場所
PY = "/opt/project-venv/bin/python"
DBT = "/opt/project-venv/bin/dbt"
PROJECT = "/opt/project"
# 取り込む7表(ingestion/schema.py の registry の名前と同じ綴り)
TABLES = [
    "orders_events",
    "order_items",
    "reviews",
    "customers",
    "sellers",
    "products",
    "product_category_name_translation",
]
# dbt に、取り込んだ日だけを窓として渡す。{{ params.target_date }} は実行時に日付へ置き換わる
# 接続のロール(transform)は dbt/profiles.yml の aws_profile_name で決まる
DBT_ARGS = (
    "--project-dir dbt --profiles-dir dbt "
    '--vars \'{start_date: "{{ params.target_date }}", end_date: "{{ params.target_date }}"}\''
)



# dbt を流す共通の形。実行前に古い結果を消し、dbt の終了コードを保存し、
# 失敗の要約を出したあとで、保存した終了コードで終わる(失敗ならタスクも失敗になる)
def dbt_with_summary(command: str) -> str:
    return (
        # 前回の run_results.json を消す(dbt が結果を書く前に落ちたとき、古い結果を読まないため)
        f"cd {PROJECT} && rm -f dbt/target/run_results.json && "
        # ; で区切るので、dbt が失敗しても次へ進む。$? は直前の終了コードで、status に保存する
        f"{DBT} {command} {DBT_ARGS}; status=$?; "
        # 失敗した項目の要約を、タスクのログに出す
        f"{PY} -m ingestion.dbt_failures dbt/target/run_results.json; "
        # 保存した dbt の終了コードで終わる
        "exit $status"
    )


with DAG(
    dag_id="olist_daily",
    schedule=None,  # 手動のみ
    start_date=datetime(2016, 9, 4),
    catchup=False,  # 過去の分をまとめて追いかけない
    # 画面で入れる日付(形は YYYY-MM-DD だけ許す)
    params={
        "target_date": Param("2016-09-04", type="string", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    },
    tags=["olist"],
    # 全タスク共通の既定値。失敗したら5分待って、最大2回やり直す(最初の実行を入れて最大3回)
    default_args={
        "retries": 2,  # やり直す回数
        "retry_delay": timedelta(minutes=5),  # やり直すまでの待ち時間
    },
) as dag:
    # 7表の取り込み。互いに関係がないので同時に流す。ローカルの data/ を読み書きするだけで、
    # AWS には触れないので、ロールの指定は要らない
    ingest_tasks = [
        BashOperator(
            task_id=f"ingest_{table}",
            bash_command=(
                f"cd {PROJECT} && {PY} -m ingestion.run_ingest --table {table} "
                "--start {{ params.target_date }} --end {{ params.target_date }}"
            ),
        )
        for table in TABLES
    ]

    # その日の Raw を S3 へ上げる。ここだけ、ingest ロールで AWS に入る
    # (AWS_PROFILE の名前は、refresh_credentials.sh が書いたファイルの見出しと同じ)
    # append_env=True: 元の環境変数(PATH など)を消さずに、足す
    upload_raw = BashOperator(
        task_id="upload_raw",
        bash_command=(
            f"cd {PROJECT} && {PY} -m ingestion.upload_raw "
            "--date {{ params.target_date }}"
        ),
        env={"AWS_PROFILE": "ecom-dev-ingest"},
        append_env=True,
    )

    # Silver を作る(窓はその日だけ)
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=dbt_with_summary("run"),
    )

    # テストを流す(同じ窓)
    # retries=0: 不合格はやり直しても直らないので、すぐ失敗として確定させる
    # (タスクに書いた値が、default_args より優先される)
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=dbt_with_summary("test"),
        retries=0,
    )

    # 順番: 7表の取り込み(同時)→ S3 へ → dbt run → dbt test
    ingest_tasks >> upload_raw >> dbt_run >> dbt_test
