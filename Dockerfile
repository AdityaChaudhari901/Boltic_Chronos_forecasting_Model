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

# Upgrade pip
RUN python -m pip install --upgrade pip

# Consolidate ALL critical dependencies into one install step
# This ensures they are all in the same environment and layer
RUN python -m pip install --no-cache-dir \
    gunicorn \
    flask \
    flask-cors \
    torch \
    pandas[pyarrow] \
    transformers \
    accelerate \
    chronos-forecasting>=2.0.0

# Install remaining requirements (backup)
RUN python -m pip install --no-cache-dir -r requirements.txt

# CRITICAL: Verify installations in build logs (If this fails, the build will stop)
RUN python -c "import flask; print(f'Flask version: {flask.__version__}')"
RUN python -c "import chronos; print('Chronos module found successfully')"
RUN python -m pip list

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
