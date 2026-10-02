#!/bin/sh
# Lanza el contenedor aislado de QA (nunca toca escaner-tqt ni su volumen). Uso: sh admin_docker.sh [imagen] [puerto]
export MSYS_NO_PATHCONV=1
IMG=${1:-qa-admin-img}; PORT=${2:-8460}
docker rm -f qa-admin >/dev/null 2>&1
docker run -d --name qa-admin -p $PORT:8443 -e TQT_HOST_IP=192.168.3.36 -e TQT_ADMIN_PASSWORD=ClaveDePrueba-123 -e TQT_BACKUP_DIR=/backups -v qa_admin_db:/data/db $IMG
