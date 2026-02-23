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
# We install to a local directory /app/deps to ensure they are bundled with the app
RUN mkdir -p /app/deps
ENV PYTHONPATH="/app/deps:${PYTHONPATH}"

RUN python3 -m pip install --no-cache-dir --target /app/deps -r requirements.txt

# CRITICAL: Verify installations in build logs
# We must include /app/deps in the path for these checks too
RUN PYTHONPATH=/app/deps python3 -c "import flask; print(f'Flask version: {flask.__version__}')"
RUN PYTHONPATH=/app/deps python3 -c "import torch; print(f'Torch version: {torch.__version__}')"
RUN PYTHONPATH=/app/deps python3 -c "import gunicorn; print(f'Gunicorn version: {gunicorn.__version__}')"
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
