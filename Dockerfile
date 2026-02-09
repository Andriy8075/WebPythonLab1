FROM python:3.14-bookworm

# Install common debugging / networking tools
RUN apt-get update && apt-get install -y \
    psmisc \
    procps \
    net-tools \
    iproute2 \
    iputils-ping \
    lsof \
    vim less nano

WORKDIR /var/www
