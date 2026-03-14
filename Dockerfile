FROM python:3.11-slim

# FFmpeg + 한글 폰트 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg fonts-nanum && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --timeout 600 --workers 1
