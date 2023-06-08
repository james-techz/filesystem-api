# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.9.16-slim-buster

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install nginx to serve public static files
RUN apt update -y
RUN apt install nginx net-tools procps vim -y
# Install pip requirements
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY ./nginx_default.conf /etc/nginx/conf.d/default.conf
COPY . /app
# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
# RUN adduser -u 1000 --disabled-password --gecos "" appuser && chown -R appuser /app
WORKDIR /app
EXPOSE 5000
# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
RUN chmod u+x start.sh
CMD ./start.sh
