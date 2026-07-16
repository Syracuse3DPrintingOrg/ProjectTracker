FROM python:3.12-slim

# adb pops the display up on Android TVs over network debugging.
RUN apt-get update && apt-get install -y --no-install-recommends adb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service/app ./app

ENV TRACKER_DATA_DIR=/data
VOLUME /data
EXPOSE 9280

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9280"]
