FROM python:3.13-alpine@sha256:1a63a53928ce53d2b0baf08092a703f4840ac5dfbd61fd48802dbf48e08c801e

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static

EXPOSE 3080

CMD ["gunicorn", "--bind=0.0.0.0:3080", "--workers=2", "--threads=4", "--timeout=30", "app:app"]
