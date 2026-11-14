"""Silver の7表を整理する(OPTIMIZE → VACUUM)。手動で実行する。

olist_daily が動いていないときに流す(MERGE の最中に重ねると、書き込みが衝突することがある)。
"""

from datetime import datetime

# タスクの部品(シェルのコマンドを1つ実行する)と、DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# プロジェクトの Python(Airflow 本体とは別の venv。イメージの中にある)と、コードの場所
PY = "/opt/project-venv/bin/python"
PROJECT = "/opt/project"

with DAG(
    dag_id="iceberg_maintenance",
    schedule=None,  # 手動のみ(一時キーが1時間で切れるので、定期実行は動かない)
    start_date=datetime(2026, 11, 14),
    catchup=False,
    tags=["olist", "maintenance"],
) as dag:
    # 7表を1つのタスクで順に整理する。Athena を使うので、transform ロールで入る
    # append_env=True: 元の環境変数(PATH など)を消さずに、足す
    BashOperator(
        task_id="optimize_and_vacuum",
        bash_command=f"cd {PROJECT} && {PY} -m ingestion.iceberg_maintenance",
        env={"AWS_PROFILE": "ecom-dev-transform"},
        append_env=True,
        # 失敗の多くは権限や設定で、5分後にやり直しても直らないので、再試行しない
        retries=0,
    )
