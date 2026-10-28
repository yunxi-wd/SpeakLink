# Python 3.11 local inference backend with audio and embedding dependencies.
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-models.txt requirements-asr.txt ./
RUN pip install --no-cache-dir -r requirements-models.txt
COPY backend ./backend
COPY configs ./configs
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
