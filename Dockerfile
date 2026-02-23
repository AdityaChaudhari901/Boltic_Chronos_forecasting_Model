FROM python:3.11-slim
WORKDIR /app

# 1. System libs
RUN apt-get update && apt-get install -y git libgomp1 && rm -rf /var/lib/apt/lists/*

# 2. Copy requirements
COPY requirements.txt .

# 3. THE FIX:
# - Use matching CPU torch/torchvision versions (2.6.0/0.21.0)
# - Install gunicorn explicitly and verify it in the SAME layer
RUN python3 -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.6.0+cpu" "torchvision==0.21.0+cpu" --extra-index-url https://pypi.org/simple && \
    python3 -m pip install --no-cache-dir -r requirements.txt && \
    python3 -m pip install --upgrade --no-cache-dir "gunicorn==25.1.0" && \
    python3 -c "import gunicorn; import torch; print('✅ Deps OK:', gunicorn.__version__)"

# 4. Copy code (start.sh is gone)
COPY . .

ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# 5. THE RUN COMMAND:
# Running as 'python3 -m gunicorn' is the secret way to fix "module not found"
CMD ["python3", "-m", "gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "300", "app:app"]