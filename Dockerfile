ARG BLENDER_IMAGE=linuxserver/blender:latest
FROM ${BLENDER_IMAGE}

USER root

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gnupg \
    python3 \
    python3-setuptools \
    python3-pip \
    curl \
    wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies into Blender's bundled Python
RUN set -eux; \
    blender_python="$(blender --background --python-expr "import sys; print('BLENDER_PYTHON=' + sys.executable)" | awk -F= '/^BLENDER_PYTHON=/{print $2; exit 0}')"; \
    if [ -z "${blender_python}" ] || [ ! -x "${blender_python}" ]; then \
        echo "Failed to detect Blender Python" >&2; \
        exit 1; \
    fi; \
    "${blender_python}" -m ensurepip; \
    "${blender_python}" -m pip install --upgrade pip; \
    "${blender_python}" -m pip install --no-cache-dir -r /tmp/requirements.txt

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

# Enable required Blender addons
RUN mkdir -p /var/lib/blender/scripts/addons/io_scene_vrm && \
    mkdir -p /var/lib/blender/config/scripts/addons

# Copy VRM addon module
COPY app/addons/vrm_addon.py /var/lib/blender/scripts/addons/io_scene_vrm/__init__.py

# Set permissions for addons
RUN chmod -R 755 /var/lib/blender/scripts/addons/io_scene_vrm && \
    echo "import bpy; bpy.ops.preferences.addon_enable(module='io_scene_gltf2')" > /var/lib/blender/config/scripts/addons/enable_addons.py && \
    chmod 755 /var/lib/blender/config/scripts/addons/enable_addons.py

# Environment variables for Blender
ENV BLENDER_USER_CONFIG="/var/lib/blender/config" \
    BLENDER_USER_SCRIPTS="/var/lib/blender/scripts" \
    BLENDER_USER_CACHE="/var/log/blender" \
    PYTHONPATH="/workspace:${PYTHONPATH}"

# Disable base entrypoint to run Blender directly
ENTRYPOINT []

# Run Blender with Python script (no GUI, background mode)
# Dockerfile内のCMDを修正 - --python-use-system-env を追加してPYTHONPATHを有効化
CMD ["blender", "--background", "--factory-startup", "--python-use-system-env", "--python", "/workspace/app/convert.py", "--debug-python", "--debug-memory"]
