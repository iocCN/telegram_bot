FROM python:3-alpine
ADD . /app
WORKDIR /app
RUN apk update \
    && apk add --no-cache build-base gcc libffi-dev libressl-dev python3-dev \
    && pip install -U setuptools pip
RUN pip install -r requirements.txt
