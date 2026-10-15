FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

# Extras to install: openai | anthropic | google | groq | ollama | postgres | all
ARG PROVIDERS=all
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra ${PROVIDERS}
COPY src ./src
RUN uv sync --frozen --no-dev --extra ${PROVIDERS}

RUN useradd -m app && mkdir -p /app/data && chown app /app/data
USER app
ENV PATH="/app/.venv/bin:$PATH"
CMD ["calorie-agent", "bot"]
