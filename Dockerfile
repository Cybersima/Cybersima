FROM python:3.12-slim

LABEL org.opencontainers.image.title="CyberSym SecureTrade 2"
LABEL org.opencontainers.image.vendor="CyberSym"
LABEL org.opencontainers.image.description="24/7 Secure Cloud Trading Engine + command-center API"

WORKDIR /app
COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
ENV SECURETRADE_DEMO_ONLY=1
CMD ["python", "-m", "securetrade", "engine", "--demo", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
