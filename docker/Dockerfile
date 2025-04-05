FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster pip installs
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN /root/.cargo/bin/uv pip install -r requirements.txt

# Copy application code
COPY . .

# Install the package in development mode
RUN /root/.cargo/bin/uv pip install -e .

# Set Python path to include our package
ENV PYTHONPATH="${PYTHONPATH}:/app"

CMD ["telltale"] 