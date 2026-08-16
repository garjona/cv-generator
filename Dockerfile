FROM python:3.11-slim

ARG INSTALL_TYPST=false
ARG INSTALL_CHROMIUM=true
ARG TYPST_VERSION=0.13.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && if [ "$INSTALL_CHROMIUM" = "true" ]; then \
      apt-get install -y --no-install-recommends chromium fonts-liberation; \
    fi \
    && if [ "$INSTALL_TYPST" = "true" ]; then \
      apt-get install -y --no-install-recommends curl xz-utils; \
      curl -fsSL -o /tmp/typst.tar.xz "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-x86_64-unknown-linux-musl.tar.xz"; \
      tar -xJf /tmp/typst.tar.xz -C /tmp; \
      mv /tmp/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst; \
      chmod +x /usr/local/bin/typst; \
      rm -rf /tmp/typst.tar.xz /tmp/typst-x86_64-unknown-linux-musl; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/outputs /app/data /app/logs

CMD ["python", "main.py", "--cv-file", "examples/sample_cv.docx", "--job-file", "examples/sample_job.html", "--pages", "1", "--render-format", "html", "--template-style", "html_ats", "--no-interactive", "--no-pdf", "--output-dir", "outputs/docker_run"]
