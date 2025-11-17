#!/bin/bash

# build and deploy script for netcup-api-filter to netcup hosting
# CRITICAL: for automated deployment, the user must have SSH keys set up and `ssh-agent` running with the key added

# 1. Build deployment package
# 2. Upload to server
# 3. Remove old content including dot-files, unzip and restart application

NETCUP_USER="hosting218629"
NETCUP_SERVER="hosting218629.ae98d.netcup.net"
REMOTE_DIR="/netcup-api-filter"

# URL where the application will be reachable
PUBLIC_FQDN="https://naf.vxxu.de/"

./build_deployment.py && \
scp deploy.zip ${NETCUP_USER}@${NETCUP_SERVER}:/ && \
ssh ${NETCUP_USER}@${NETCUP_SERVER} \
    "cd / && rm -rf ${REMOTE_DIR}/* ${REMOTE_DIR}/.[!.]* ${REMOTE_DIR}/..?* && mkdir -p ${REMOTE_DIR}/tmp/ && unzip -o -u deploy.zip -d ${REMOTE_DIR}/ && touch ${REMOTE_DIR}/tmp/restart.txt"
    