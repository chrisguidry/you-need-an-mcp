FROM python:3.15-slim AS builder

# uv comes from its image by tag and digest, so Dependabot can bump it and
# the final image never holds it.
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /uvx /bin/

# Compile bytecode at build time because the final stage runs as a user that
# cannot write it, and copy packages because the cache is not in the final
# stage. The system Python is the same one the final stage uses.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app
COPY . .
RUN uv sync --locked --no-dev

FROM python:3.15-slim

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

# The final image never installs packages. pip vendors old copies of urllib3,
# msgpack, and setuptools that scanners report.
RUN pip uninstall -y pip

# The virtual environment refers to /app by path, so it keeps that location.
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 65532 is the conventional nobody user. The server writes nothing at runtime
# and listens on port 9000, so it needs no privileges.
USER 65532:65532

EXPOSE 9000

ENTRYPOINT ["tini", "--"]
CMD ["python", "-c", "import server; server.mcp.run(transport='http', host='0.0.0.0', port=9000)"]
