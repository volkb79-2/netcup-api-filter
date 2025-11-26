FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy canonical application package
COPY src/ ./src/

# Copy configuration template
COPY config.example.yaml ./config.example.yaml

# Ensure Python can import the src package
ENV PYTHONPATH="/app/src"

# Expose port
EXPOSE 5000

# Run the application via the canonical module entrypoint
CMD ["python", "-m", "netcup_api_filter.filter_proxy", "/app/config.yaml"]
