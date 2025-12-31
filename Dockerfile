# Use Ubuntu base image
FROM ubuntu:24.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates gnupg && \
    apt-get update && apt-get install -y \
    wget \
    unzip \
    xz-utils \
    python3 \
    curl \ 
    python3-setuptools \
    python3-pip \
    # X11関連のライブラリ
    libxrender1 \
    libxcursor1 \
    libxi6 \
    libxrandr2 \
    libxinerama1 \
    libxxf86vm1 \
    libxkbcommon0 \
    # Session Management ライブラリ
    libsm6 \
    libxext6 \
    libx11-6 \
    libice6 \
    # OpenGLライブラリ
    libgl1 \
    libglu1-mesa \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Download and install Blender
RUN wget https://download.blender.org/release/Blender4.3/blender-4.3.0-linux-x64.tar.xz  \
    && tar -xf blender-4.3.0-linux-x64.tar.xz \
    && mv blender-4.3.0-linux-x64 /usr/local/blender \
    && rm blender-4.3.0-linux-x64.tar.xz

# Set up environment variables
ENV BLENDER_PATH="/usr/local/blender"
ENV BLENDER_PYTHON="${BLENDER_PATH}/4.3/python/bin/python3.11"
ENV PATH="${BLENDER_PATH}:${BLENDER_PYTHON}:${PATH}"
ENV PYTHONPATH="/usr/local/blender/4.3/scripts/addons:${PYTHONPATH}"

# Install Python dependencies
RUN ${BLENDER_PYTHON} -m ensurepip && \
    ${BLENDER_PYTHON} -m pip install --upgrade pip && \
    ${BLENDER_PYTHON} -m pip install --no-cache-dir \
    Flask \
    requests \
    pillow \
    numpy \
    urllib3 \
    redis

# Enable required Blender addons
RUN mkdir -p /usr/local/blender/4.3/scripts/addons/io_scene_vrm && \
    mkdir -p /usr/local/blender/4.3/config/scripts/addons

# Copy VRM addon module
COPY app/addons/vrm_addon.py /usr/local/blender/4.3/scripts/addons/io_scene_vrm/__init__.py

# Set permissions for addons
RUN chmod -R 755 /usr/local/blender/4.3/scripts/addons/io_scene_vrm && \
    echo "import bpy; bpy.ops.preferences.addon_enable(module='io_scene_gltf2')" > /usr/local/blender/4.3/config/scripts/addons/enable_addons.py && \
    chmod 755 /usr/local/blender/4.3/config/scripts/addons/enable_addons.py

# Set default environment variables
ENV REDIS_HOST=redis \
    REDIS_PORT=6379 \
    # MAX_FILE_SIZE=52428800 \
    RATE_LIMIT_REQUESTS=10 \
    RATE_LIMIT_WINDOW=60 \
    CONVERSION_TIMEOUT=300 \
    CACHE_DURATION=3600

# Set the working directory
WORKDIR /app

# Create and set permissions for temporary and output directories
RUN mkdir -p /tmp/convert /app/output && \
    chmod 777 /tmp/convert /app/output && \
    chown nobody:nogroup /tmp/convert /app/output

# Copy the conversion script
COPY ./app/convert.py /app/convert.py

# Expose the port
EXPOSE 5000

# Set up directories and permissions
RUN mkdir -p /var/log/blender /var/lib/blender/config /var/lib/blender/scripts && \
    chmod -R 777 /var/log/blender /var/lib/blender

# Environment variables for Blender
ENV BLENDER_USER_CONFIG="/var/lib/blender/config" \
    BLENDER_USER_SCRIPTS="/var/lib/blender/scripts" \
    BLENDER_USER_CACHE="/var/log/blender" \
    BLENDER_SYSTEM_SCRIPTS="/usr/local/blender/4.3/scripts" \
    BLENDER_SYSTEM_PYTHON="/usr/local/blender/4.3/python" \
    OCIO="/usr/local/blender/4.3/datafiles/colormanagement/config.ocio"

# Run Blender with Python script (no GUI, background mode)
# CMD ["/usr/local/blender/blender", "--background", "--factory-startup", "--python-use-system-env", "--python", "/usr/local/blender/4.3/config/scripts/addons/enable_addons.py", "--python", "/app/convert.py"]
# Dockerfile内のCMDを修正
CMD ["/usr/local/blender/blender", "--background", "--factory-startup", "--python", "/app/convert.py", "--debug-python", "--debug-memory"]
