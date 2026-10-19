FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools \
    iptables \
    iproute2 \
    curl \
    qrencode \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    WG_DATA_DIR=/app/data \
    WG_CONF_PATH=/etc/wireguard/wg0.conf \
    WEBUI_PORT=8000 \
    WEBUI_HOST=0.0.0.0

EXPOSE 8000 51820/udp

VOLUME ["/etc/wireguard", "/app/data"]

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]
