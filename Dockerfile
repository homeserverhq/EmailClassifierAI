FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create a non-privileged user and group
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser

# Ensure the application directory is owned by this user
# Assuming your app is in /app
RUN chown -R appuser:appuser /app

# Switch to the non-privileged user
USER appuser

# Ensure the launcher is executable and has correct line endings
RUN chmod +x /app/launcher.sh && sed -i 's/\r$//' /app/launcher.sh

# Set the shell for the container
SHELL ["/bin/bash", "-c"]
