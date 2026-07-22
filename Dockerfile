FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system adoptai && useradd --system --gid adoptai --home-dir /app adoptai

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=adoptai:adoptai . .
COPY docker-entrypoint.sh /usr/local/bin/adoptai-entrypoint
RUN chmod 755 /usr/local/bin/adoptai-entrypoint \
    && mkdir -p /var/lib/adoptai/uploads \
    && chown -R adoptai:adoptai /var/lib/adoptai

USER adoptai
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

ENTRYPOINT ["adoptai-entrypoint"]
