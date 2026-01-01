FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY . /app

RUN uv pip install --system -e ".[dev]"

ENV PYTHONUNBUFFERED=1

