# 土台: 公式の Airflow 3.3.2(Python 3.12。手元の uv と同じ版の Python)
FROM apache/airflow:3.3.2-python3.12

# uv を、公式のイメージから1ファイルだけコピーする(版は手元と同じ 0.10.8)
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv

# uv の設定(公式の写し。流してよい): 作る venv の場所、Python をダウンロードしない、
# ファイルはリンクでなくコピー、.pyc を先に作って起動を速くする
ENV UV_PROJECT_ENVIRONMENT=/opt/project-venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# venv を /opt に作るため、いったん管理者(root)になる
USER root
WORKDIR /opt/project

# 依存の定義だけをコピーする(コードは、あとでマウントで見せる)
COPY pyproject.toml uv.lock ./

# uv.lock どおりに、プロジェクトの venv を作る(Airflow 本体の環境とは別。版がぶつからない)
#   --frozen: uv.lock を書き換えない(手元と同じ版を保証)
#   --no-dev: pytest や ruff などの開発用は入れない
#   --no-install-project: プロジェクト自身はインストールしない(コードはマウントで渡す)
#   --python: イメージにある Python 3.12 の本体を使う(公式イメージでは /usr/python にある。
#             Airflow 本体は、そこから作った別の venv /home/airflow/.local に入っている)
RUN uv sync --frozen --no-dev --no-install-project --python /usr/python/bin/python3.12

# 元の場所と利用者(airflow)に戻す。Airflow は root で動かさない
WORKDIR /opt/airflow
USER airflow
