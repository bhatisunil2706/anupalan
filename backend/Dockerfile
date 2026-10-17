FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd --uid 1001 --create-home app && mkdir -p /app/storage && chown -R app /app/storage
USER app
EXPOSE 8000
# Migrations run separately (the `migrate` service) with the owner role; the app connects as the restricted
# runtime role. Proxy headers are trusted because the backend is only reachable from the web container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
