# Use Python 3.9+ slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies for pandapower and numerical computing
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create output directories
RUN mkdir -p /app/output /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port for dashboard if applicable
EXPOSE 8050

# Default command (can be overridden)
CMD ["python", "grid_simulation_toolkit.py"]
