# Build riproducibile del Celery exporter dal commit verificato usato dal progetto.
FROM python:3.14-slim-bookworm

ARG CELERY_EXPORTER_COMMIT=d45a395e03a0209ba288f99477060619ec1341f3
ARG CELERY_EXPORTER_SHA256=c61b78f91b7175eb08aaaac8c70bdcef24b76d4abf74db728ff086173600bef1

ADD --checksum=sha256:${CELERY_EXPORTER_SHA256} \
    https://github.com/danihodovic/celery-exporter/archive/${CELERY_EXPORTER_COMMIT}.tar.gz \
    /tmp/celery-exporter.tar.gz

RUN mkdir /app \
    && tar -xzf /tmp/celery-exporter.tar.gz --strip-components=1 -C /app \
    && pip install --no-cache-dir /app \
    && rm /tmp/celery-exporter.tar.gz \
    && adduser --disabled-password --gecos "" exporter \
    && chown -R exporter:exporter /app

USER exporter
EXPOSE 9808
ENTRYPOINT ["python", "/app/cli.py"]
