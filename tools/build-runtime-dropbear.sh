#!/bin/sh
# Build dropbear for the M7350 (ARM, dynamic against the
# device glibc: a static glibc cannot resolve root through NSS).
# Source: Debian trixie dropbear 2025.89 (apt-get source verifies it against
# the signed archive); upstream tarball sha256 pinned below.
# Called by build-runtime.sh after input hash verification.
set -eu
work=$1
inputs=$2
cc=$3
prefix=${cc%gcc}
mkdir "$work/dropbear"
cd "$work/dropbear"
tar -xf "$inputs/dropbear_2025.89.orig.tar.bz2" --strip-components=1
cat > localoptions.h <<'EOF'
/* M7350: key-only root login over USB; nothing else. */
#define DROPBEAR_SVR_PASSWORD_AUTH 0
#define DROPBEAR_SVR_PAM_AUTH 0
#define DROPBEAR_CLI_PASSWORD_AUTH 0
#define DROPBEAR_X11FWD 0
#define DROPBEAR_SVR_AGENTFWD 0
#define DROPBEAR_CLI_AGENTFWD 0
#define DROPBEAR_SVR_REMOTETCPFWD 0
#define DROPBEAR_SVR_LOCALTCPFWD 0
#define DSS_PRIV_FILENAME "/data/m7350-l2/ssh/dropbear_dss_host_key"
#define RSA_PRIV_FILENAME "/data/m7350-l2/ssh/dropbear_rsa_host_key"
#define ECDSA_PRIV_FILENAME "/data/m7350-l2/ssh/dropbear_ecdsa_host_key"
#define ED25519_PRIV_FILENAME "/data/m7350-l2/ssh/dropbear_ed25519_host_key"
#define DROPBEAR_PIDFILE "/run/m7350-l2/dropbear.pid"
#define DEFAULT_PATH "/usr/bin:/bin:/usr/sbin:/sbin"
#define DROPBEAR_DSS 0
#define DROPBEAR_ECDSA 0
#define DROPBEAR_RSA 0
#define DROPBEAR_ED25519 1
EOF
PATH=$(dirname "$cc"):$PATH CC="$cc" CFLAGS="-Os -march=armv7-a -mfloat-abi=soft" \
    ./configure --host=arm-linux-gnueabi --disable-zlib --disable-pam --disable-lastlog \
    --disable-utmp --disable-utmpx --disable-wtmp --disable-wtmpx --disable-loginfunc \
    --disable-pututline --disable-pututxline --disable-syslog >/dev/null
PATH=$(dirname "$cc"):$PATH make -j"${JOBS:-2}" PROGRAMS="dropbear dropbearkey scp" MULTI=1 >/dev/null
"${prefix}strip" -o "$work/runtime/bin/dropbearmulti" dropbearmulti
