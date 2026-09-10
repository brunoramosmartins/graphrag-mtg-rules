# The application container: the Python runtime the ETL, retrieval and
# evaluation commands run in, so a clean machine needs Docker and nothing
# else. Neo4j and Phoenix are separate services; see docker-compose.yml.
#
# The image holds the **code**. `data/` and `runs/` are bind-mounted from
# the repo at run time, so the 196 MB of downloaded sources and the vector
# cache survive `docker compose down` and are the same files the host venv
# uses — nobody downloads the corpus twice to have it in two places.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, and from the metadata alone. `pyproject.toml`
# changes rarely and `src/` changes constantly, so resolving and
# installing 200 MB of wheels is its own layer and a code edit does not
# re-run it. `packages.find` needs a package directory to exist, hence the
# one `__init__.py`; the real tree arrives below and the editable install
# picks it up without reinstalling.
#
# `[tracing]`, not `[observability]`: the latter adds Arize Phoenix, which is
# the *viewer* — a server this stack runs as its own compose service. Bundling
# it here would put a web application, pandas and SQLAlchemy into an image
# whose job is to export spans over HTTP, at roughly double the size.
COPY pyproject.toml README.md LICENSE ./
COPY src/graphrag_mtg/__init__.py ./src/graphrag_mtg/
RUN pip install -e ".[tracing]"

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# uid 1000 is the first non-system user on a typical Linux host, so files
# this container writes into the bind-mounted `data/` and `runs/` belong to
# the person who cloned the repo rather than to root. On Docker Desktop the
# mount is remapped and the uid is not consulted, so this costs nothing
# there. If your host uid differs, `docker compose run --user $(id -u) app`.
RUN useradd --uid 1000 --create-home --shell /bin/bash app \
    && mkdir -p /app/data /app/runs \
    && chown -R app:app /app
USER app

# A workspace, not a server: every command here is one you run against it
# (`docker compose exec app python scripts/bootstrap.py`). Phase 8's
# Streamlit demo replaces this with the server it starts, and the service
# stops needing an explanation.
CMD ["sleep", "infinity"]
