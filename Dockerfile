FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home appuser
USER appuser
ENV RETRIEVAL_BACKEND=demo
EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/health/live')"
CMD ["python", "-m", "retrieval_mcp", "--host", "0.0.0.0", "--port", "8050"]
