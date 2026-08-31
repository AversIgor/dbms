FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY src ./src
COPY alembic ./alembic

RUN pip install --no-cache-dir .

ENV ALEMBIC_INI=/app/alembic.ini

EXPOSE 8080

# Одна реплика: upgrade и HTTP в одном процессе (статус последнего upgrade в памяти).
CMD ["migrate", "serve", "--upgrade"]
