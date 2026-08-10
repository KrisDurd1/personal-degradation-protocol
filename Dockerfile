FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /srv
COPY bot ./bot
COPY docs ./docs
RUN pip install --no-cache-dir -e ./bot

WORKDIR /srv/bot
CMD ["python", "-m", "app.main"]
