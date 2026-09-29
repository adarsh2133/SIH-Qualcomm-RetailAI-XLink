#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$(id -un)}"
VENV="${APP_DIR}/.venv-ncnn"
MODEL_DIR="${APP_DIR}/models/yolo/best_ncnn_model"
SERVICE_FILE="/etc/systemd/system/portal-xlink.service"
STATE_DIR="/var/lib/portal-xlink"

if [[ "${EUID}" -eq 0 && -z "${SUDO_USER:-}" ]]; then
  echo "Run this installer as the Pi application user, not directly as root." >&2
  exit 2
fi
if [[ "${APP_DIR}" == *" "* ]]; then
  echo "Install the project in a path without spaces (for example /home/${APP_USER}/PORTAL-XLINK)." >&2
  exit 2
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd is required; this installer supports Raspberry Pi OS." >&2
  exit 2
fi
if [[ ! -d "${MODEL_DIR}" ]] ||
   ! compgen -G "${MODEL_DIR}/*.param" >/dev/null ||
   ! compgen -G "${MODEL_DIR}/*.bin" >/dev/null; then
  echo "NCNN model files are missing from ${MODEL_DIR}." >&2
  echo "Export/copy the trained model files (.param and .bin) there, then rerun." >&2
  exit 2
fi

sudo apt-get update
sudo apt-get install -y python3-venv python3-dev swig liblgpio-dev openssl v4l-utils i2c-tools libgl1 libglib2.0-0
if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/python" -m pip install --upgrade pip
"${VENV}/bin/python" -m pip uninstall -y opencv-python opencv-contrib-python
"${VENV}/bin/python" -m pip install -r "${APP_DIR}/requirements-pi.txt"
mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs"
sudo install -d -o "${APP_USER}" -g "$(id -gn "${APP_USER}")" -m 0700 "${STATE_DIR}"

cat <<UNIT | sudo tee "${SERVICE_FILE}" >/dev/null
[Unit]
Description=PORTAL-XLINK Raspberry Pi camera and alert service
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=PORTAL_INFERENCE_BACKEND=ncnn
Environment=PORTAL_NCNN_MODEL_PATH=${MODEL_DIR}
Environment=PORTAL_STATE_DIR=${STATE_DIR}
Environment=PORTAL_DB_PATH=${STATE_DIR}/retail.db
Environment=PORTAL_LOGS_PATH=${STATE_DIR}/logs/app.log
Environment=PORTAL_API_HOST=0.0.0.0
Environment=PORTAL_API_PORT=8765
Environment=PORTAL_CAMERA_COUNT=4
Environment=PORTAL_LCD_INTERFACE=auto
ExecStart=${VENV}/bin/python ${APP_DIR}/app.py --serve-api
Restart=on-failure
RestartSec=10
TimeoutStopSec=20
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

for group in video i2c gpio; do
  if getent group "${group}" >/dev/null; then
    sudo usermod -aG "${group}" "${APP_USER}"
  fi
done
sudo systemctl daemon-reload
sudo systemctl enable --now portal-xlink.service
echo "PORTAL-XLINK service installed and started."
echo "Check status with: sudo systemctl status portal-xlink.service"
echo "View first-run pairing approval with: sudo journalctl -u portal-xlink.service -n 40"
if [[ -t 0 ]]; then
  read -r -p "Run guided LCD detection/setup now? [y/N] " configure_lcd
  if [[ "${configure_lcd,,}" == "y" || "${configure_lcd,,}" == "yes" ]]; then
    (cd "${APP_DIR}" && sudo "${VENV}/bin/python" -m hardware.lcd_setup)
  fi
fi
