FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    gnuplot \
    git \
    lcov \
    libgeos-dev \
    libopenmpi-dev \
    libproj-dev \
    openmpi-bin \
    openmpi-common \
    openmpi-doc \
    poppler-utils \
    pkg-config \
    proj-bin \
    proj-data \
    screen \
    python-is-python3 \
    python3 \
    python3-dev \
    python3-pip \
    sudo \
    unzip \
    wget \
  && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

RUN pip install --no-cache-dir \
    numpy \
    astropy \
    ephem \
    networkx \
    sgp4 \
    geopy \
    matplotlib \
    statsmodels \
    cartopy

RUN pip install --no-cache-dir \
    git+https://github.com/snkas/exputilpy.git@v1.6 \
    git+https://github.com/snkas/networkload.git@v1.3 \
    gurobipy

WORKDIR /workspaces/SatComHypatia-frog

CMD ["bash"]
