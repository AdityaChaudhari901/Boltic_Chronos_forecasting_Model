# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip
RUN python -m pip install --upgrade pip

# Consolidate ALL critical dependencies into one install step
# 1. Use CPU-only torch to prevent builder OOM (signal: killed)
# 2. Install gunicorn explicitly and verify it in the SAME layer
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.10.0+cpu" "torchvision==0.21.0+cpu" --extra-index-url https://pypi.org/simple && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    python3 -m pip install --upgrade --no-cache-dir "gunicorn==25.1.0" && \
    python3 -c "import gunicorn; import torch; from chronos import Chronos2Pipeline; print('✅ All dependencies verified')"

# Copy model and application code
COPY finetuned_chronos_forecasting/ ./finetuned_chronos_forecasting/
COPY app.py .

# Expose port
EXPOSE 8080

# Set environment variables
ENV PORT=8080
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Critical fix for PyTorch/macOS/Linux fork safety in containers
ENV OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Run the application
# We use start.sh for a robust, platform-proof boot sequence.
CMD ["/app/start.sh"]
