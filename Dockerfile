# AWS Lambda with Playwright pre-compiled
FROM public.ecr.aws/lambda/python:3.12

# Update system and install minimal required packages
RUN dnf update -y && dnf install -y \
    alsa-lib \
    atk \
    cairo \
    cups-libs \
    fontconfig \
    freetype \
    gdk-pixbuf2 \
    gtk3 \
    libX11 \
    libXcomposite \
    libXcursor \
    libXdamage \
    libXext \
    libXfixes \
    libXi \
    libXinerama \
    libXrandr \
    libXrender \
    libXtst \
    libgbm \
    libpng \
    libxcb \
    pango && \
    dnf clean all

# Set Playwright cache directory
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN mkdir -p /opt/pw-browsers

# Install Poetry and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir poetry

# Copy and install project dependencies
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# Install Playwright and Chromium (untuk scraper modules)
RUN pip install --no-cache-dir playwright && \
    playwright install chromium

# Copy source code
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Default handler (akan di-override oleh image_config.command di Lambda)
CMD ["src.entrypoint.handlers.scraper_handler"]
