#!/bin/sh
# provider mode: runs the ordered steps in provider.d/.
set -u
here=$(dirname "$0")
exec sh "$here/steps.sh" "$(dirname "$here")/provider.d" "${1:-}"
