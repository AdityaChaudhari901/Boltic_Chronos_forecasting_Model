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
# We switch to CPU-only torch to prevent builder OOM (signal: killed)
# and install to /app/deps to ensure they are available at runtime.
RUN mkdir -p /app/deps
ENV PYTHONPATH="/app/deps:${PYTHONPATH}" \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --target /app/deps --index-url https://download.pytorch.org/whl/cpu "torch==2.10.0+cpu" "torchvision==0.21.0+cpu" --extra-index-url https://pypi.org/simple && \
    python3 -m pip install --target /app/deps -r requirements.txt && \
    PYTHONPATH=/app/deps python3 -c "import torch; import gunicorn; import flask; print('✅ All dependencies verified in /app/deps')"

# CRITICAL: Verify installations in build logs
RUN PYTHONPATH=/app/deps python3 -c "from chronos import Chronos2Pipeline; print('Chronos2Pipeline imported successfully')"
RUN PYTHONPATH=/app/deps python3 -m pip list

# Copy model and application code
# Path updated to match our fine-tuned name
COPY finetuned_chronos_forecasting/ ./finetuned_chronos_forecasting/
COPY app.py .
COPY start.sh .

# Ensure start.sh is executable
RUN chmod +x start.sh

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
