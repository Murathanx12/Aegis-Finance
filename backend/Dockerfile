FROM python:3.12-slim

WORKDIR /app

# System deps for lightgbm, scipy, hmmlearn
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip for better retry handling
RUN pip install --upgrade pip

# Install heavy ML packages first (most likely to timeout)
RUN pip install --no-cache-dir --timeout 300 \
    numpy pandas scipy scikit-learn lightgbm shap

# Install remaining deps
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --timeout 120 -r backend/requirements.txt

# Copy application code
COPY backend/ backend/
COPY engine/ engine/

# Port from env (Railway sets PORT)
ENV PORT=8000

EXPOSE ${PORT}

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
