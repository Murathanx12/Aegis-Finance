FROM python:3.12-slim

WORKDIR /app

# System deps for lightgbm, scipy, hmmlearn
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip for better retry handling
RUN pip install --upgrade pip

# Install all deps in one layer with generous timeout
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --prefer-binary --timeout 600 --retries 10 -r backend/requirements.txt

# Copy application code
COPY backend/ backend/
COPY engine/ engine/

COPY .dockerignore .dockerignore

# Frozen population registration package; no operating task starts in the API.
COPY scripts/branch_population.py scripts/local_branching.py scripts/local_branching_task.py scripts/local_branching_grade_child.py scripts/beta_v1_news_capture.py scripts/
COPY scripts/world_digest_provisional.py scripts/world_digest_provisional.py
COPY docs/TRIALS/POPULATION-1000-SOURCES.json docs/TRIALS/POPULATION-1000-SPECIFICATIONS.json docs/TRIALS/TRIAL-POPULATION-1000-20261015.md docs/TRIALS/
# The public-assets health probe reads this committed pin at /app/scripts/.
COPY scripts/render_public_assets.py scripts/render_public_assets.py

# The IC reader's path is source-pinned by the prepared PC policy epoch. In
# Railway, bind that path to the already provisioned /data volume instead of
# changing policy-pinned Python. A missing volume file stays missing.
RUN ln -sfn /data/funnel_night10.json /app/backend/data/funnel_night10.json

# Port from env (Railway sets PORT)
ENV PORT=8000

# glibc arena bloat guard (2026-07-16): the 80-ticker screener runs numpy MC
# across 8 worker threads; default glibc grows up to 8*ncores malloc arenas
# and freed pages never return to the OS — Railway bills that plateau as
# RAM-hours. 2 arenas is the standard fix for threaded numpy services
# (negligible lock contention at our request volume).
ENV MALLOC_ARENA_MAX=2

EXPOSE ${PORT}

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
