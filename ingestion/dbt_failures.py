"""dbt の run_results.json から、失敗した項目だけを取り出して、1行ずつ表示する。"""

import json
import sys
from pathlib import Path

# 失敗とみなす status。モデルの失敗は error、テストの不合格は fail(実行できない場合は error)
FAILED = {"error", "fail"}


def failed_lines(path: Path) -> list[str]:
    """run_results.json を読み、失敗した項目を「種類 名前 status メッセージ」の1行にして返す。"""
    # JSON ファイルを読み込み、辞書にする
    data = json.loads(path.read_text())
    lines = []
    # results には、モデルとテストの1件ずつの結果が並んでいる
    for result in data["results"]:
        # 成功(success / pass)と、飛ばされたもの(skip)は出さない
        if result["status"] not in FAILED:
            continue
        # unique_id は「種類.プロジェクト名.名前(.末尾の識別子)」。種類と名前だけ取り出す
        parts = result["unique_id"].split(".")
        kind, name = parts[0], parts[2]
        # message は複数行のことがあるので、1行にまとめて、長すぎたら200文字で切る
        message = " ".join((result.get("message") or "").split())[:200]
        lines.append(f"  {kind:<6} {name}  {result['status']}  {message}")
    return lines


def main(argv: list[str]) -> int:
    """要約を標準出力に出す。dbt 自身の終了コードは DAG 側で守るので、ここは常に 0 を返す。"""
    path = Path(argv[1])
    # dbt が結果を書く前に落ちたときは、ファイルがない(古い結果を読まないよう、DAG 側で消してある)
    if not path.exists():
        print("[dbt] run_results.json がありません(dbt が結果を書く前に失敗した)")
        return 0
    lines = failed_lines(path)
    # 失敗があるときだけ、見出しと一覧を出す
    if lines:
        print(f"[dbt FAILED] {len(lines)}件")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
