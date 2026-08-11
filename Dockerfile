FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Кириллица для справки: в slim-образе шрифтов нет вообще
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY bot ./bot
COPY docs ./docs
RUN pip install --no-cache-dir -e ./bot

WORKDIR /srv/bot
CMD ["python", "-m", "app.main"]
