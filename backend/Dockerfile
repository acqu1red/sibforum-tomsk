FROM python:3.12-slim AS badge-fonts
RUN apt-get update \
    && apt-get install -y --no-install-recommends cabextract ca-certificates curl \
    && curl -fsSL --retry 2 --max-time 25 https://downloads.sourceforge.net/corefonts/times32.exe -o /tmp/times32.exe \
    && echo 'db56595ec6ef5d3de5c24994f001f03b2a13e37cee27bc25c58f6f43e8f807ab  /tmp/times32.exe' | sha256sum -c - \
    && cabextract -F 'Times.TTF' -d /fonts /tmp/times32.exe \
    && cabextract -F 'Timesbd.TTF' -d /fonts /tmp/times32.exe \
    && test -s /fonts/Times.TTF && test -s /fonts/Timesbd.TTF

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY --from=badge-fonts /fonts/ /usr/local/share/fonts/badge/

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

EXPOSE 8100
CMD ["python", "manage.py", "runserver", "0.0.0.0:8100"]
