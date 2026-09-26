FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
# Ingest the corpus at start-up so the image works with a mounted corpus/laws volume.
CMD python -m fitihai.cli ingest && uvicorn fitihai.api:app --host 0.0.0.0 --port ${PORT}
