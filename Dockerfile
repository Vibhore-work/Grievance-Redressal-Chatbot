FROM ghcr.io/astral-sh/uv:alpine

# Install build dependencies for compiling Python packages
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    python3-dev \
    build-base

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync

COPY . .

EXPOSE 5050
CMD ["uv", "run", "app.py"]
