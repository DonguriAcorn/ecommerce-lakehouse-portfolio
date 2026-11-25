#!/usr/bin/env bash
# Airflow のコンテナに渡す一時キーを、手元(Mac)で発行し直すスクリプト(ADR 0012)
# 使い方: プロジェクト直下で bash airflow/refresh_credentials.sh(Airflow を使う前に毎回)

# 失敗したら止める(-e)、未定義の変数はエラー(-u)、パイプの途中の失敗も拾う(pipefail)
set -euo pipefail

# 書き出す先(リポジトリの外。Git に上がる心配がない)
OUT_DIR="${HOME}/.ecom-airflow"
OUT_FILE="${OUT_DIR}/credentials"
# 借りるロールのプロファイル(手元の ~/.aws/config と同じ名前。dbt と ingestion はこの名前で探す)
PROFILES=(ecom-dev-ingest ecom-dev-transform ecom-prod-ingest ecom-prod-transform)

# フォルダを作り、自分だけが入れるようにする(700)
mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"

# いったん同じフォルダの一時ファイルに書き、最後に名前を変えて差し替える(書きかけを見せない)
TMP_FILE="$(mktemp "${OUT_DIR}/credentials.XXXXXX")"
# 途中で失敗したら、一時ファイルを消す
trap 'rm -f "${TMP_FILE}"' EXIT

for profile in "${PROFILES[@]}"; do
  # 管理者の鍵でロールを借り、一時キーを「名前=値」の行で取り出す
  creds="$(aws configure export-credentials --profile "${profile}" --format env-no-export)"

  # 3つの値(キー ID、秘密のキー、セッションのトークン)を、credentials ファイルの形に直す
  #   例: AWS_ACCESS_KEY_ID=ASIA... → aws_access_key_id = ASIA...
  section="$(printf '%s\n' "${creds}" | awk '
    /^AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)=/ {
      key = tolower(substr($0, 1, index($0, "=") - 1))   # 「=」より前を小文字にする
      val = substr($0, index($0, "=") + 1)                # 「=」より後ろ(値に = があっても崩れない)
      print key " = " val
    }')"

  # 3行そろわなければ、壊れたファイルを作らずに止める
  if [ "$(printf '%s\n' "${section}" | grep -c ' = ')" -ne 3 ]; then
    echo "失敗: ${profile} の一時キーを取り出せませんでした" >&2
    exit 1
  fi

  # プロファイルの見出しと3行を、一時ファイルに足す
  printf '[%s]\n%s\n\n' "${profile}" "${section}" >> "${TMP_FILE}"

  # 期限だけを表示する(キーの値は表示しない)
  expiry="$(printf '%s\n' "${creds}" | sed -n 's/^AWS_CREDENTIAL_EXPIRATION=//p')"
  echo "${profile}: 期限 ${expiry:-不明}"
done

# 自分だけが読めるようにしてから、本物のファイルと差し替える
chmod 600 "${TMP_FILE}"
mv "${TMP_FILE}" "${OUT_FILE}"
echo "書き出し: ${OUT_FILE}"
