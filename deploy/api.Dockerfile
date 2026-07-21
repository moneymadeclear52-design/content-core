# API image for the content platform (content-core[api]).
FROM python:3.11-slim
WORKDIR /app
COPY . /app/content-core
RUN pip install --no-cache-dir "/app/content-core[api,db]"
RUN mkdir -p /data
EXPOSE 8000
# readiness: run migrations then serve
CMD ["sh", "-c", "alembic -c /app/content-core/alembic.ini upgrade head || true; uvicorn content_core.api.app:app --host 0.0.0.0 --port 8000"]
