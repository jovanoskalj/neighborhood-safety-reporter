# Use official Python image
FROM python:3.13-slim

# Don't write .pyc cache files
ENV PYTHONDONTWRITEBYTECODE=1
# Force stdout/stderr to be unbuffered for logs
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . .
