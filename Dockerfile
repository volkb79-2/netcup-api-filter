FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY filter_proxy.py .
COPY netcup_client.py .
COPY access_control.py .

# Copy configuration template
COPY config.example.yaml .

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "filter_proxy.py", "/app/config.yaml"]
