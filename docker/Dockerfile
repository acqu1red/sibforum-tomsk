FROM python:3.12-slim

WORKDIR /app
COPY server/server.py /app/server/server.py
COPY site /app/site

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    HOST=0.0.0.0 \
    PORT=8095 \
    DATA_DIR=/app/data

EXPOSE 8095
CMD ["python", "server/server.py"]
