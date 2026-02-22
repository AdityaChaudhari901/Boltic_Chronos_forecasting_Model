# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Force cache bust for pip install
ARG CACHEBUST=1

# Install Python dependencies
RUN pip install --no-cache-dir gunicorn
RUN pip install --no-cache-dir -r requirements.txt

# Verify installation in build logs
RUN pip list

# Copy model and application code
# Path updated to match our fine-tuned name
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
# Using gunicorn for production stability on Boltic. 
# We use 'python -m gunicorn' to ensure the binary is easily found in the python path.
CMD ["sh", "-c", "OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES python -m gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 300 app:app"]
