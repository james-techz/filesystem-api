# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.9.16-slim-buster

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install nginx to serve public static files
RUN --mount=type=cache,target=/var/cache/apt apt update -y && apt install net-tools procps ffmpeg fluidsynth -y 


# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN mkdir /app && adduser -u 1000 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser
COPY . /app
WORKDIR /app
# Install pip requirements
COPY requirements.txt .
# RUN --mount=type=cache,target=/home/appuser/.local python -m pip install --upgrade pip
# RUN --mount=type=cache,target=/home/appuser/.local python -m pip install -r requirements.txt
RUN python -m pip install --upgrade pip
RUN python -m pip install -r requirements.txt

EXPOSE 5000
# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
ENV PATH=$PATH:/home/appuser/.local/bin
CMD ./start.sh
