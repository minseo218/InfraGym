FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS test

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests

CMD ["python", "-m", "pytest", "-q"]

FROM base AS runtime

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY app ./app

RUN groupadd --system --gid 10001 infragym \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent infragym \
    && mkdir -p /data \
    && chown -R infragym:infragym /app /data
ENV INFRAGYM_DB_PATH=/data/infragym.db

USER infragym
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
