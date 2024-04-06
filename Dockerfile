### BASE STAGE ###
FROM python:3.8.18-slim-bullseye AS base-stage
# Keeps Python from generating .pyc files in the container
# ENV PYTHONDONTWRITEBYTECODE=1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1
# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN mkdir /app && adduser -u 1000 --disabled-password --gecos "" appuser && chown -R appuser /app

### BASE-DEPLOY STAGE ###
FROM base-stage AS base-deploy-stage
RUN --mount=type=cache,target=/var/cache/apt apt-get update && apt-get install openssh-client git net-tools procps ffmpeg fluidsynth -y


### BASE_BUILD STAGE ###
FROM base-deploy-stage AS base-build-stage
RUN --mount=type=cache,target=/var/cache/apt apt-get update && apt-get install autoconf automake pkg-config libtool build-essential libasound2-dev libjack-dev portaudio19-dev -y 

### BUILD STAGE ### 
FROM base-build-stage as build-stage
USER appuser
# Install pip requirements
WORKDIR /home/appuser
RUN --mount=type=cache,target=/home/appuser/.cache/pip,uid=1000,gid=1000 python3 -m pip install --upgrade pip
COPY tensorflow-2.7.4-cp38-cp38-manylinux2010_x86_64.whl .
RUN --mount=type=cache,target=/home/appuser/.cache/pip,uid=1000,gid=1000 python3 -m pip install ./tensorflow-2.7.4-cp38-cp38-manylinux2010_x86_64.whl
COPY requirements.txt .
RUN --mount=type=cache,target=/home/appuser/.cache/pip,uid=1000,gid=1000 python3 -m pip install -r requirements.txt


### DEPLOY STAGE ###
FROM base-deploy-stage as deploy-stage
USER appuser
# Copy pre-built python environment
COPY --from=build-stage /home/appuser/.local /home/appuser/.local
# Copy code
COPY *.py *.conf *.txt *.sh *.mag Dockerfile /app/
WORKDIR /app
EXPOSE 5000
# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
ENV PATH=$PATH:/home/appuser/.local/bin
CMD ./start.sh
