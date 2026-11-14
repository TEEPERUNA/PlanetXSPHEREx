FROM python:3.12-slim
WORKDIR /app
COPY science/requirements.txt science/requirements.txt
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY science science
COPY backend backend
ENV OUTPUT_DIR=/data/output PER_GROUP=3 WARMUP=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
