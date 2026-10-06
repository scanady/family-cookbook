# The engine with everything it shells out to, for running `cookbook` where it
# is not installed: Chromium (lays out and prints the pages), Ghostscript
# (compresses the press PDF), and poppler (reads PDF pages for ingest). Fonts
# ship inside the package.
#
# Built for linux/amd64. It has no ENTRYPOINT or CMD: run
# `cookbook ... --book /work/<book>` yourself.
#
#   docker buildx build --platform linux/amd64 -t family-cookbook .
#   docker run --rm -v "$PWD/my-book:/work/book" family-cookbook cookbook press --book /work/book
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends ghostscript poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/engine
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . \
 && python -m playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* \
 && cookbook --version

WORKDIR /work
