FROM python:3.13-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Dipendenze di sistema minime richieste da psycopg2 (build) e Pillow/lxml (parsing/immagini).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libxml2-dev \
    libxslt1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Installiamo dal lock senza il progetto locale: il codice viene copiato dopo,
# così una modifica Python non forza il download dell'intero stack ONNX e
# Playwright. uv usa inoltre molta meno memoria del resolver pip su Docker
# Desktop, evitando i crash osservati con Python 3.13.
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-dev --no-emit-project --format requirements-txt \
       --output-file /tmp/requirements.txt \
    && uv pip install --system --no-cache --requirement /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# I due binari coprono percorsi distinti: Chromium serve DynamicFetcher e la
# modalità stealth standard; `real_chrome=true` seleziona invece il canale
# Google Chrome di Patchright, installato nel percorso di sistema sottostante.
RUN playwright install --with-deps chromium \
    && patchright install chromium \
    && patchright install chrome \
    && test -x /opt/google/chrome/chrome

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN groupadd --system app \
    && useradd --system --gid app --create-home app \
    && chown -R app:app /app /ms-playwright

USER app

EXPOSE 8000

# I worker Celery (scraping/media/ai) e Celery Beat riusano questa stessa immagine
# con comando diverso, definito nel docker-compose a livello di repo (non gestito qui).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
