FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PRICEWATCH_DB=/data/pricewatch.db
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable && useradd --create-home watcher && mkdir /data && chown watcher /data
USER watcher
VOLUME /data

ENTRYPOINT ["/app/.venv/bin/pricewatch"]
CMD ["watch"]
