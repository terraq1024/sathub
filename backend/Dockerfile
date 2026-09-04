FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1

# gdal runtime libs for rasterio wheels
RUN apt-get update     && apt-get install -y --no-install-recommends libgdal-dev     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Migrate, create the first admin from env credentials, then serve.
CMD ["sh", "-c", "python manage.py migrate && python manage.py bootstrap_admin && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 300"]
