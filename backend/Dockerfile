# Build from the project root: docker build -f backend/Dockerfile .

# --- Stage 1: build the React/Vite frontend into static assets ---
# Without this stage, the final image would only have raw frontend/src
# (JSX, unbundled ESM imports) with no build step to turn it into something
# a browser can run — main.py's static-file fallback would serve source
# files with the wrong content type instead of a working UI.
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# --- Stage 2: backend + the built frontend ---
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
# --prefer-binary: avoid pip choosing an older/different version that lacks
# a prebuilt wheel and falling back to a source build (this bit us during
# development — a resolver backtrack landed on a blis version with no
# wheel for the target Python, which failed a Cython compile). Doesn't
# change *which* packages get installed, just avoids that failure mode.
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY backend/ .
# main.py resolves the frontend at /frontend (see FRONTEND_DIR in main.py:
# three parents up from backend/app/main.py lands at the container's /).
# Only the built dist/ is needed at runtime, not the frontend source.
COPY --from=frontend-build /frontend/dist /frontend/dist

# Pre-download embedding/reranker (and, if enabled, table-layout) models at
# build time. Without this, the first real request after container start
# would trigger a live Hugging Face download — a bad failure mode for a
# demo in front of judges if the network is slow or restricted.
RUN python scripts/warm_models.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
