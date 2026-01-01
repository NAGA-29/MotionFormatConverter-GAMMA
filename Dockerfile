# Use Ubuntu base image
FROM ubuntu:22.04

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
RUN wget https://download.blender.org/release/Blender5.0/blender-5.0.1-linux-x64.tar.xz   \
    && tar -xf blender-5.0.1-linux-x64.tar.xz \
    && mv blender-5.0.1-linux-x64 /usr/local/blender \
    && rm blender-5.0.1-linux-x64.tar.xz

# Set up environment variables
ENV BLENDER_PATH="/usr/local/blender"
ENV BLENDER_PYTHON="${BLENDER_PATH}/5.0/python/bin/python3.11"
ENV PATH="${BLENDER_PATH}:${BLENDER_PYTHON}:${PATH}"
ENV PYTHONPATH="/usr/local/blender/5.0/scripts/addons:${PYTHONPATH}"

# Copy requirements file
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN ${BLENDER_PYTHON} -m ensurepip && \
    ${BLENDER_PYTHON} -m pip install --upgrade pip && \
    ${BLENDER_PYTHON} -m pip install --no-cache-dir -r /tmp/requirements.txt

# Enable required Blender addons
RUN mkdir -p /usr/local/blender/5.0/scripts/addons/io_scene_vrm && \
    mkdir -p /usr/local/blender/5.0/config/scripts/addons

# Copy VRM addon module
COPY app/addons/vrm_addon.py /usr/local/blender/5.0/scripts/addons/io_scene_vrm/__init__.py

# Set permissions for addons
RUN chmod -R 755 /usr/local/blender/5.0/scripts/addons/io_scene_vrm && \
    echo "import bpy; bpy.ops.preferences.addon_enable(module='io_scene_gltf2')" > /usr/local/blender/5.0/config/scripts/addons/enable_addons.py && \
    chmod 755 /usr/local/blender/5.0/config/scripts/addons/enable_addons.py

# Set default environment variables
ENV REDIS_HOST=redis \
    REDIS_PORT=6379 \
    # MAX_FILE_SIZE=52428800 \
    RATE_LIMIT_REQUESTS=10 \
    RATE_LIMIT_WINDOW=60 \
    CONVERSION_TIMEOUT=300 \
    CACHE_DURATION=3600

# Set the working directory
WORKDIR /workspace

# Create and set permissions for temporary and output directories
RUN mkdir -p /tmp/convert /workspace/output && \
    chmod 777 /tmp/convert /workspace/output && \
    chown nobody:nogroup /tmp/convert /workspace/output

# Copy the entire app directory
COPY ./app /workspace/app

# Expose the port
EXPOSE 5000

# Set up directories and permissions
RUN mkdir -p /var/log/blender /var/lib/blender/config /var/lib/blender/scripts && \
    chmod -R 777 /var/log/blender /var/lib/blender

# Environment variables for Blender
ENV BLENDER_USER_CONFIG="/var/lib/blender/config" \
    BLENDER_USER_SCRIPTS="/var/lib/blender/scripts" \
    BLENDER_USER_CACHE="/var/log/blender" \
    BLENDER_SYSTEM_SCRIPTS="/usr/local/blender/5.0/scripts" \
    BLENDER_SYSTEM_PYTHON="/usr/local/blender/5.0/python" \
    OCIO="/usr/local/blender/5.0/datafiles/colormanagement/config.ocio" \
    PYTHONPATH="/workspace:${PYTHONPATH}"

# Run Blender with Python script (no GUI, background mode)
# Dockerfile内のCMDを修正 - --python-use-system-env を追加してPYTHONPATHを有効化
CMD ["/usr/local/blender/blender", "--background", "--factory-startup", "--python-use-system-env", "--python", "/workspace/app/convert.py", "--debug-python", "--debug-memory"]
