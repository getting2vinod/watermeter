FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY app ./app
RUN mkdir -p /app/data/uploads/water
EXPOSE 4006
CMD ["/app/.venv/bin/uvicorn","app.main:app","--host","0.0.0.0","--port","4006"]
