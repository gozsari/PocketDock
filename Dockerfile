FROM condaforge/miniforge3:latest

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV P2RANK_HOME=/opt/p2rank
ENV PATH="${P2RANK_HOME}:${PATH}"

# Install JRE + wget; force-unsafe-io works around Docker Desktop fsync bug on macOS
RUN echo 'force-unsafe-io' > /etc/dpkg/dpkg.cfg.d/docker-no-fsync && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        default-jre-headless wget \
    && rm -rf /var/lib/apt/lists/*

# Install P2Rank v2.5
RUN wget -q https://github.com/rdk/p2rank/releases/download/2.5/p2rank_2.5.tar.gz -O /tmp/p2rank.tar.gz \
    && mkdir -p /opt/p2rank \
    && tar -xzf /tmp/p2rank.tar.gz -C /opt/p2rank --strip-components=1 \
    && rm -f /tmp/p2rank.tar.gz \
    && chmod +x /opt/p2rank/prank

# Install AutoDock Vina v1.2.7 binary (detect architecture)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        VINA_URL="https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_linux_x86_64"; \
    elif [ "$ARCH" = "arm64" ]; then \
        VINA_URL="https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_linux_aarch64"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    wget -q "$VINA_URL" -O /usr/local/bin/vina && \
    chmod +x /usr/local/bin/vina

# Install scientific packages via conda (official distribution channel)
RUN mamba install -y -c conda-forge \
    python=3.11 rdkit openmm pdbfixer \
    numpy scipy \
    && mamba clean -afy

WORKDIR /app

# Install web framework and remaining packages via pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles /app/data

RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

CMD ["gunicorn", "pocketdock.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
