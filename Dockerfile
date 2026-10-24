FROM python:3.13-slim

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . .
RUN uv sync --locked --no-dev

# The final image never installs packages. pip vendors old copies of urllib3,
# msgpack, and setuptools that scanners report.
RUN pip uninstall -y pip

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 9000

ENTRYPOINT ["tini", "--"]
CMD ["python", "-c", "import server; server.mcp.run(transport='http', host='0.0.0.0', port=9000)"]
