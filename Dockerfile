# Use the Alpine-based n8n image from DockerHub
FROM n8nio/n8n:latest

# Install Python3 + pip + pipeline dependencies
USER root
RUN apk add --no-cache python3 py3-pip jq && \
  python3 -m pip install --break-system-packages --no-cache-dir \
  google-genai \
  requests && \
  mkdir -p /data && chown -R node:node /data
USER node