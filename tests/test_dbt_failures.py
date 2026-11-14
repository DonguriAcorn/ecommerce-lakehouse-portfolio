"""ingestion/dbt_failures.py(dbt の失敗の要約)のテスト。"""

import json
from pathlib import Path

from ingestion.dbt_failures import failed_lines, main


def write_results(path: Path, results: list[dict]) -> Path:
    """見本の run_results.json を書く。results の各項目は status / unique_id / message だけ持つ。"""
    path.write_text(json.dumps({"results": results}))
    return path


def test_only_failed_items_are_listed(tmp_path):
    # 成功・不合格・実行エラー・スキップが混ざった結果を作る
    path = write_results(
        tmp_path / "run_results.json",
        [
            {"status": "pass", "unique_id": "test.proj.ok_test.abc", "message": None},
            {
                "status": "fail",
                "unique_id": "test.proj.not_null_x.abc",
                "message": "Got 3 results,\nconfigured to fail if != 0",
            },
            {"status": "error", "unique_id": "model.proj.silver_y", "message": "Database Error"},
            {"status": "skipped", "unique_id": "model.proj.silver_z", "message": None},
        ],
    )
    lines = failed_lines(path)
    # 失敗の2件だけが出る(成功とスキップは出ない)
    assert len(lines) == 2
    # 種類・名前・status が入り、メッセージの改行は1行にまとまる
    assert "test" in lines[0] and "not_null_x" in lines[0] and "fail" in lines[0]
    assert "Got 3 results, configured to fail if != 0" in lines[0]
    assert "model" in lines[1] and "silver_y" in lines[1] and "error" in lines[1]


def test_nothing_is_printed_when_all_succeed(tmp_path, capsys):
    # 全部成功の結果
    path = write_results(
        tmp_path / "run_results.json",
        [{"status": "pass", "unique_id": "test.proj.ok_test.abc", "message": None}],
    )
    code = main(["dbt_failures", str(path)])
    # 何も表示せず、終了コードは 0
    assert code == 0
    assert capsys.readouterr().out == ""


def test_missing_file_is_reported(tmp_path, capsys):
    # dbt が結果を書く前に落ちた場合(ファイルがない)
    code = main(["dbt_failures", str(tmp_path / "nothing.json")])
    # 「ありません」の1行が出て、終了コードは 0
    assert code == 0
    assert "run_results.json がありません" in capsys.readouterr().out
