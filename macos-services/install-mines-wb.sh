#!/bin/bash
# First-time setup = enable (like systemctl enable --now).
exec bash "$(cd "$(dirname "$0")" && pwd)/enable-mines-wb.sh"
