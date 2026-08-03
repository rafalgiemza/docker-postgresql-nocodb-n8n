FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY seed_app.py .

# Data volume (Excel file mounted from outside)
VOLUME ["/data"]

EXPOSE 8000

CMD ["python", "seed_app.py"]
