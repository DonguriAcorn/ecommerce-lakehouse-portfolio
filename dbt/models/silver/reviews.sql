-- Silver の reviews: レビュー×注文ごとに1行(キーは レビュー ID + 注文 ID)
-- 同じレビューが複数の注文に付く例がある(789 件、中身は同じ)。注文とのつながりを残すため、組をキーにする
-- 窓・merge・full_refresh=false・パーティションなしの考え方は order_items.sql と同じ
{% set keys = ['review_id', 'order_id'] %}

{{ config(
    incremental_strategy='merge',
    unique_key=keys,
    full_refresh=false
) }}

-- 共通の部品で、キーごとに最後に届いた1行にする
{{ silver_latest(
    'reviews',
    keys=keys,
    columns=['review_id', 'order_id', 'review_score', 'review_comment_title',
             'review_comment_message', 'review_creation_date', 'review_answer_timestamp']
) }}
