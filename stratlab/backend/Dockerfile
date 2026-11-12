# The backend's image: Python from Docker Hub and the packages from PyPI only, so a deploy doesn't depend on downloading build tools from
# GitHub (8 Nov 2026: three Railway builds failed while fetching the nixpacks/railpack drivers and mise from GitHub releases).
# The fonts the decks use are in app/fonts; every package installs from a wheel, so no compiler or system library is needed.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# The app runs as its own unprivileged user. The code and the packages stay root's and read-only to it: at run time it writes
# only temporary files (the system temp directory), and its caches are in memory. The home directory is its own.
RUN useradd --create-home --uid 10001 --user-group --shell /usr/sbin/nologin app
USER 10001:10001
# railway.json's startCommand runs the app; this is the same command for a plain `docker run`
CMD ["sh", "-c", "PYTHONMALLOC=${PYTHONMALLOC:-malloc} uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
