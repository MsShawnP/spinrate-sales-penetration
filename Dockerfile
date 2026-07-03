FROM python:3.11-slim AS base

WORKDIR /app

# Install vendored packages first (change less often)
COPY packages/lailara-palette/ /app/packages/lailara-palette/
RUN pip install --no-cache-dir /app/packages/lailara-palette/

# Install app dependencies
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .

# Copy application code
COPY app/ /app/app/
COPY assets/ /app/assets/
COPY wsgi.py /app/

EXPOSE 8050

CMD ["gunicorn", "wsgi:server", "--bind", "0.0.0.0:8050", "--workers", "2", "--timeout", "120"]
