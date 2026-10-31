"""取り込みの出来事を、JSON Lines で記録する。"""

import json
from datetime import datetime, timezone
from pathlib import Path


class RunLog:
    """1回の実行の出来事を、1行 = 1件の JSON で書く。"""

    def __init__(self, log_dir: Path, table: str, batch_id: str) -> None:
        self.table = table
        self.batch_id = batch_id
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        message = f"[{stage}] {what}"
        if column is not None:
            message += f" / {column}"
        if count is not None:
            message += f" / {count}件"
        if samples:
            message += f" (例: {', '.join(samples)})"

        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(message)
