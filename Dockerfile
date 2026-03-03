# Use the official n8n image directly
FROM docker.n8n.io/n8nio/n8n:latest

# No build-time steps to avoid exit code 127
USER root
RUN mkdir -p /data && chown -R node:node /data
USER node