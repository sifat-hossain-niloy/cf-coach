FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0.30" \
    "alembic>=1.13" "psycopg[binary]>=3.2" "httpx>=0.27" "pydantic>=2.7" "pydantic-settings>=2.3"
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
