FROM python:3.10-slim
WORKDIR /app

# Copy requirements first to leverage Docker caching
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -y ffmpeg
# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install torch==2.1.0+cpu --extra-index-url https://download.pytorch.org/whl/cpu


# Copy the rest of the application
COPY . .

# Expose the Flask app port
EXPOSE 5000


# Start the Flask app
CMD ["python", "main.py"]