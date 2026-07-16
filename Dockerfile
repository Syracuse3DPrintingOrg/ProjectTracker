FROM python:3.12-slim

WORKDIR /app
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service/app ./app

ENV TRACKER_DATA_DIR=/data
VOLUME /data
EXPOSE 9280

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9280"]
