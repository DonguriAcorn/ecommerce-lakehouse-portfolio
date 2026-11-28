"""upload_logs のテスト。AWS には繋がず、ファイルの選び方とキーの形だけ確かめる。"""

from pathlib import Path

from ingestion.upload_logs import find_log_files, find_quarantine_files, s3_key

# 同じ表のログの相対パス(日付と batch_id だけ変えて使う)
ORDERS = "ingest/olist/orders_events/run_date={d}/batch_id={b}/events.jsonl"
REVIEWS = "ingest/olist/reviews/run_date={d}/batch_id={b}/events.jsonl"
# 隔離ファイルの相対パス(data/quarantine/ の下の形)
Q_ORDERS = "olist/orders_events/run_date={d}/batch_id={b}/orders_events.parquet"


def _make(log_dir: Path, rel: str) -> Path:
    # 空のログファイルを、フォルダごと作る
    f = log_dir / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{}\n")
    return f


def test_find_log_files_picks_only_the_run_date(tmp_path):
    # 指定した日のログを2表ぶんと、別の日のログを1つ置く
    want1 = _make(tmp_path, ORDERS.format(d="2026-11-14", b="a"))
    want2 = _make(tmp_path, REVIEWS.format(d="2026-11-14", b="b"))
    _make(tmp_path, ORDERS.format(d="2026-11-13", b="c"))
    # 指定した日の2つだけが、名前順で返る
    assert find_log_files(tmp_path, "2026-11-14") == [want1, want2]


def test_find_log_files_returns_empty_when_no_logs(tmp_path):
    # ログが1つもない日は、空のリスト(main はこれを失敗として扱う)
    assert find_log_files(tmp_path, "2026-11-14") == []


def test_s3_key_keeps_the_local_layout(tmp_path):
    f = _make(tmp_path, ORDERS.format(d="2026-11-14", b="a"))
    # ローカルの場所の前に logs/ が付くだけ
    assert s3_key(tmp_path, f) == (
        "logs/ingest/olist/orders_events/run_date=2026-11-14/batch_id=a/events.jsonl"
    )


def test_find_quarantine_files_picks_only_the_run_date(tmp_path):
    # 指定した日の隔離ファイルを1つと、別の日のものを1つ置く
    want = _make(tmp_path, Q_ORDERS.format(d="2026-11-14", b="a"))
    _make(tmp_path, Q_ORDERS.format(d="2026-11-13", b="b"))
    # 指定した日の1つだけが返る
    assert find_quarantine_files(tmp_path, "2026-11-14") == [want]


def test_find_quarantine_files_returns_empty_on_normal_day(tmp_path):
    # 隔離のない日は空のリスト(main はこれを失敗にしない)
    assert find_quarantine_files(tmp_path, "2026-11-14") == []


def test_s3_key_for_quarantine(tmp_path):
    f = _make(tmp_path, Q_ORDERS.format(d="2026-11-14", b="a"))
    # ローカルの場所の前に quarantine/ が付くだけ(error-handling.md の置き場所と同じ形)
    assert s3_key(tmp_path, f, "quarantine") == (
        "quarantine/olist/orders_events/run_date=2026-11-14/batch_id=a/orders_events.parquet"
    )
