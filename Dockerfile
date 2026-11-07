# The mobile website, for any Docker host. The Streamlit app is unaffected and still deploys from requirements.txt.
# Stage 1 ranks the dropped leads once, so the running server needs neither pandas nor scikit-learn.
FROM python:3.11-slim AS scores
WORKDIR /app
RUN pip install --no-cache-dir "pandas>=2.2" "scikit-learn>=1.5" "pydantic>=2.7" "python-dotenv>=1.0"
COPY core ./core
COPY data ./data
COPY web/__init__.py web/build_scores.py ./web/
RUN python -m web.build_scores

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1 UDYAM_DB=/tmp/udyam.db PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home app
WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY core ./core
COPY data ./data
COPY web ./web
COPY --from=scores /app/web/lead_scores.json ./web/lead_scores.json
USER app
EXPOSE 10000
# One worker: sessions live in memory, and OCR already runs one at a time.
CMD ["sh", "-c", "uvicorn web.server:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 30"]
