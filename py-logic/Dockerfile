FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY price_data.py .
COPY worker.py .
COPY main.py .
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "worker.py"]
