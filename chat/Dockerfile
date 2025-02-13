FROM ubuntu:latest

WORKDIR /work

RUN apt-get update && \
    apt-get install -y iputils-ping net-tools python3 python3-pip

RUN pip install Flask Flask_SocketIO --break-system-packages
