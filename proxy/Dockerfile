FROM python:3.11-slim

ENV MITMPROXY_HOME=/home/mitmproxy/.mitmproxy
WORKDIR /proxy

# Install system dependencies required by mitmproxy and media handling
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libffi-dev \
       libssl-dev \
       libxml2-dev \
       libxslt1-dev \
       libjpeg-dev \
       zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy proxy script and Python requirements
COPY PodBlockProxy.py requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create mitmproxy config dir and verify version
RUN mkdir -p $MITMPROXY_HOME \
 && mitmproxy --version

VOLUME ["/home/mitmproxy/.mitmproxy"]

# Default upstream PodBlock server; override at runtime with -e PODBLOCK_SERVER
ENV PODBLOCK_SERVER="http://host.docker.internal:5001"

# Expose mitmproxy listening and web UI ports
EXPOSE 8080 8081

# Launch mitmproxy (web UI) with immediate streaming (no buffering)
CMD ["mitmweb", \
     "--web-host", "0.0.0.0", \
     "--web-port", "8081", \
     "--listen-host", "0.0.0.0", \
     "--listen-port", "8080", \
     "--quiet", \
     "--set", "stream_large_bodies=1", \
     "--set", "chunk_size=8kb", \
     "-s", "PodBlockProxy.py" \
    ]
