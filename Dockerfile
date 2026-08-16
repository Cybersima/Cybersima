# syntax=docker/dockerfile:1

FROM node:22-bookworm AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt gunicorn

COPY backend/ /app/backend/
COPY --from=frontend /src/frontend/dist /app/frontend/dist

ENV LOCKWELL_FRONTEND_DIST=/app/frontend/dist
ENV HOST=0.0.0.0
ENV PORT=5000
ENV FLASK_DEBUG=0
ENV SECRET_KEY=change-me-in-production
ENV MONITOR_PEPPER=change-me-in-production

WORKDIR /app/backend
RUN mkdir -p /app/backend/instance
EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "app:app"]
