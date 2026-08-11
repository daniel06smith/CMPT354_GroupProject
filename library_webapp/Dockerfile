FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Cloud Run injects $PORT — gunicorn binds to it
ENV PORT=8080

EXPOSE 8080

CMD gunicorn --bind "0.0.0.0:$PORT" --workers 1 --timeout 60 app:app
