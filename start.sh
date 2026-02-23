#!/bin/sh
set -e

# Port handling for Boltic
PORT=${PORT:-8080}

echo "🚀 Booting Chronos Forecasting Service..."
echo "Interpreter: $(which python3)"
echo "Python Version: $(python3 --version)"

# Verification of gunicorn
if ! python3 -c "import gunicorn; print('✅ gunicorn ok', gunicorn.__version__)" ; then
    echo "❌ CRITICAL: gunicorn could not be imported. sys.path is:"
    python3 -c "import sys; print(sys.path)"
    exit 1
fi

# Verification of chronos
if ! python3 -c "from chronos import Chronos2Pipeline; print('✅ chronos ok')" ; then
    echo "❌ CRITICAL: chronos-forecasting could not be imported."
    exit 1
fi

echo "Environment Verified. Starting Gunicorn..."

exec python3 -m gunicorn \
  --bind 0.0.0.0:${PORT} \
  --workers 1 \
  --timeout 300 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  app:app
