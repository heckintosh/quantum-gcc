FROM ubuntu:latest

RUN apt-get update && \
    apt-get install -y iputils-ping net-tools python3 python3-scapy