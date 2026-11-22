{% docs gmv %}
GMV(流通総額)。売上を表す指標で、明細の `price + freight_value`(商品代 + 送料)の合計。
`is_counted` が true の注文だけを数える(canceled と unavailable は外す)。
進行中(shipped、processing など)の注文は含める。為替は使わず、通貨はレアル(BRL)のまま。
{% enddocs %}

{% docs repeat_rate %}
リピート率。注文のある本人のうち、2注文以上した本人の割合(分子 = 2注文以上の本人の数、分母 = 注文のある本人の数)。
本人は `customer_unique_id` で数える。`customer_id` は注文ごとに振り直されるため、同じ人でも別の ID になり、使うとリピートを見落とす。
{% enddocs %}

{% docs order_count %}
注文数。`fact_orders` の注文(`order_id`)の数で、`is_counted` が true の注文だけを数える。
GMV と同じく、canceled と unavailable は外し、進行中は含める。
{% enddocs %}

{% docs avg_order_amount %}
平均注文額。GMV ÷ 注文数。分子の GMV も分母の注文数も、`is_counted` が true の注文だけで数える。
{% enddocs %}
