"""取り込みの出来事を、JSON Lines で記録する。"""

import json
from datetime import UTC, datetime
from pathlib import Path


class RunLog:
    """1回の実行の出来事を、1行 = 1件の JSON で書く。"""

    def __init__(self, log_dir: Path, table: str, batch_id: str) -> None:
        # ログの各行に入れるので、覚えておく
        self.table = table
        self.batch_id = batch_id
        # 実行した日(UTC)。フォルダ名に使う
        run_date = datetime.now(UTC).strftime("%Y-%m-%d")
        # ログの置き場所。実行ごとに別のファイルになる
        # (例: logs/ingest/olist/orders/run_date=2026-11-03/batch_id=.../events.jsonl)
        self.path = (
            log_dir
            / "ingest"
            / "olist"
            / table
            / f"run_date={run_date}"
            / f"batch_id={batch_id}"
            / "events.jsonl"
        )

    def write(
        self,
        level: str,
        stage: str,
        code: str,
        what: str,
        column: str | None = None,
        count: int | None = None,
        samples: list[str] | None = None,
        ingest_date: str | None = None,
    ) -> None:
        """出来事を1行書き、同じ内容の message を画面にも出す。"""
        # 人が読む1行の文を組み立てる。値があるものだけを、順に後ろへ足す
        message = f"[{stage}] {what}"
        if column is not None:
            message += f" / {column}"
        if count is not None:
            message += f" / {count}件"
        if samples:
            message += f" (例: {', '.join(samples)})"

        # ファイルに書く1件分の記録。あとで機械が検索・集計できるよう、項目に分けておく
        record = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": level,
            "batch_id": self.batch_id,
            "table": self.table,
            "stage": stage,
            "code": code,
            "ingest_date": ingest_date,
            "column": column,
            "count": count,
            "samples": samples,
            "message": message,
        }
        # フォルダがなければ作る
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # "a": 追記モード。前の出来事を消さず、末尾に1行足す
        with self.path.open("a", encoding="utf-8") as f:
            # ensure_ascii=False: 日本語を \uXXXX にせず、そのまま書く。改行で1件を区切る
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        # 同じ内容を画面にも出す(実行中に様子が分かるように)
        print(message)
