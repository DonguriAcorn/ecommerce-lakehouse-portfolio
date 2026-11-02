#!/usr/bin/env bash
# Claude が Bash で打つコマンドを、実行の前に見張る(PreToolUse の hook)。
# 危ない形なら、終了コード 2 で止め、理由を stderr に出す(stderr は Claude に届く)。
# settings.json の deny は文字列の照合だけなので、言い方を変えた形をここで止める。
set -uo pipefail

block() {
  echo "guard-bash: 止めました($1)。必要なら、ユーザーにターミナルで打ってもらってください。" >&2
  exit 2
}

command -v jq >/dev/null || block "jq がないので、コマンドを確かめられない"

# 入力の JSON から、コマンドの文字列を取り出す
cmd=$(jq -r '.tool_input.command // empty') || block "入力の JSON を読めない"
# 改行とタブを空白にし、続く空白を1つにまとめる(照合しやすくするため)
cmd=$(printf '%s' "$cmd" | tr '\n\t' '  ' | tr -s ' ')

# 照合: パターンに当たれば 0 を返す
has() { printf '%s' "$cmd" | grep -Eq -- "$1"; }

# ; & | をまたがない、1つのコマンドの中の文字
s='[^;&|]*'

# --- git ---
has "git ${s}add${s} (-[a-zA-Z]*[fAu]|--force|--all|--update|\.|\./|:/|\*)( |$)" \
  && block "git add のまとめての追加か、.gitignore を無視する追加"
has "git ${s}commit${s} (-[a-zA-Z]*a[a-zA-Z]*|--all)( |$)" \
  && block "git commit -a(ステージしていない変更までコミットする)"
has "git ${s}push${s} (-f|--force[a-z-]*)( |$|=)" \
  && block "git push の強制(公開の履歴を書き換える)"

# --- terraform ---
has "terraform ${s}(apply|destroy|import|force-unlock|console)( |$)" \
  && block "terraform で AWS か状態を変えるコマンド(ユーザーが打つ)"
has "terraform ${s}(show|output|state)( |$)" \
  && block "terraform の状態の中身を出すか、変えるコマンド(メールなどが平文で出る)"

# --- aws ---
has "aws ${s}s3 (rm|rb|mv)( |$)" && block "S3 のオブジェクトかバケットを消す"
has "aws ${s}s3 ${s}--delete" && block "S3 の sync --delete(先のファイルを消す)"
has "aws ${s} delete-[a-z-]+" && block "AWS のリソースを消す(delete-*)"
has "aws ${s}configure (get|export-credentials)( |$)" && block "AWS の認証情報を出す"
if has "aws ${s}athena ${s}start-query-execution"; then
  printf '%s' "$cmd" | grep -Eiq 'drop |delete from|truncate ' \
    && block "Athena で DROP / DELETE(Iceberg ではデータも消える)"
fi

# --- 秘密のファイル(どのコマンドからでも、名前を出したら止める) ---
has "\.tfvars|\.tfstate|(^|[ /'\"=])\.env([ .'\"]|$)|~/\.aws|\.aws/|~/\.ssh|\.ssh/|secrets\.toml" \
  && block "秘密のファイルかフォルダの名前を含む"

exit 0
