# Stage 1: Base build stage
FROM python:3.13-slim AS builder
 
# Create the app directory
RUN mkdir /app
 
# Set the working directory
WORKDIR /app

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Mexico_City

# Install dependencies first for caching benefit
RUN pip install --upgrade pip 
COPY requirements.txt /app/ 
RUN pip install --no-cache-dir -r requirements.txt
# Stage 2: Production stage
FROM python:3.13-slim
 
RUN useradd -m -r appuser && \
   mkdir /app && \
   chown -R appuser /app
 
# Copy the Python dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*

RUN chown -R appuser /usr/local/lib/python3.13/site-packages/django/contrib/auth/migrations

# Set the working directory
WORKDIR /app
 
# Copy application code
COPY --chown=appuser:appuser . .
 
# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Mexico_City
 
# Switch to non-root user
USER appuser
 
# Expose the application port
EXPOSE 8000 

# Make entry file executable
RUN chmod +x  /app/entrypoint.prod.sh
# Start the application using Gunicorn
CMD ["/app/entrypoint.prod.sh"]