---
name: tf-plan
description: terraform plan を実行し、結果を初学者向けに読み解く(件数の予想、リソースごとの説明、削除と置き換えの理由、GUI で変わる場所)。apply はユーザーに任せる。Terraform のファイルを変えたあとや、/tf-plan で使う。
argument-hint: "[フォルダ 例: terraform/envs/dev]"
---

# terraform plan の読み解き

対象のフォルダ: $ARGUMENTS(空なら、直前に変えた .tf のフォルダ。分からなければ AskUserQuestion で聞く)

1. 実行の前に、予想を書く: 追加・変更・削除の件数と、その理由(どの .tf のどの変更から来るか)。
2. `terraform -chdir=<フォルダ> plan -no-color -input=false` を実行する。plan は AWS を変えないので、Claude が実行してよい。
3. 結果を、この順で示す。
   - 1行目: `Plan: X to add, Y to change, Z to destroy.` と、予想との違い
   - リソースごとの表: 記号(`+` 追加、`~` 変更、`-` 削除、`-/+` 置き換え)、リソース名、かんたんな言葉での意味、なぜ出たか
   - 変わる属性は、主なものだけを「変える前 → 変えたあと」で示す。長い出力は要点だけにする
4. `-` か `-/+` があれば、必ず理由を説明し、データが消えるか(S3 の中身、Glue のテーブル、Iceberg のデータ)を書く。意図しない削除なら、apply に進まない。
5. apply のあと、マネジメントコンソールのどこで結果を確かめるかを書く。
6. apply は、ユーザーがターミナルで打つ。打つコマンドを示す: `terraform -chdir=<フォルダ> apply`(.claude/settings.json の deny で、Claude は apply できない)。
