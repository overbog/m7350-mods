#!/bin/sh
# home mode: runs the ordered steps in home.d/.
set -u
here=$(dirname "$0")
exec sh "$here/steps.sh" "$(dirname "$here")/home.d" "${1:-}"
