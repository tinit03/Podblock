FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into the image
COPY . .

# Expose port for Flask
EXPOSE 5000

# tell Flask CLI what to run
ENV FLASK_APP=main.py \
    FLASK_ENV=production

# Start the Flask server
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000", "--no-reload"]
