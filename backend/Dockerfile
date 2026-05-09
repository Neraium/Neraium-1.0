FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY neraium_core ./neraium_core

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn app.main:app --host ${BACKEND_HOST:-0.0.0.0} --port ${BACKEND_PORT:-8080}"]
