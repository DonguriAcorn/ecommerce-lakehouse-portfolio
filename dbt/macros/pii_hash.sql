-- 個人情報の列を、salt を混ぜた SHA-256 のハッシュにする(元には戻せない。同じ値は、いつも同じハッシュになる)
-- 使い方: pii_hash('c.customer_unique_id') のように、列の名前を文字で渡す
-- salt は環境変数 PII_SALT から読む。既定値は付けない(未設定なら dbt が止まり、salt なしの弱いハッシュを防ぐ)
-- 注意: salt は SQL の文章に入るため、dbt のログ・target/compiled/・Athena のクエリ履歴に残る(設計書に限界として書く)
{% macro pii_hash(column_name) %}
    to_hex(sha256(to_utf8(
        '{{ env_var("PII_SALT") }}' || cast({{ column_name }} as varchar)
    )))
{% endmacro %}
