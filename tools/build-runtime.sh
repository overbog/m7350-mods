#!/bin/sh
# Rebuild the ARM runtime offline in a clean Debian x86-64 build environment.
set -eu
if [ "$#" != 2 ]; then
    echo "usage: $0 INPUT_DIR NEW_WORK_DIR" >&2
    exit 2
fi
repo=$(CDPATH='' cd "$(dirname "$0")/.." && pwd)
inputs=$(realpath "$1")
work=$(realpath -m "$2")
jobs=${JOBS:-2}
experiment=$repo/experiments/oem-ipsec
zx=$repo/experiments/rtl8192es-zx
(cd "$inputs" && sha256sum -c "$repo/tools/runtime-inputs.sha256")
mkdir "$work"
cd "$work"
mkdir -p toolchains runtime/ko runtime/bin
tar -xf "$inputs/linaro-mirror.tar.xz" -C toolchains
# Kbuild supplies its own headers. Omit this toolchain's target libc sysroot,
# which contains absolute symlinks and is unnecessary for kernel modules.
tar --exclude='*/arm-linux-gnueabihf/libc' -xf "$inputs/gcc492.tar.gz" -C toolchains
set -- "$work"/toolchains/arm-linux-gnueabihf-*/bin/arm-linux-gnueabihf-gcc
kernel_cc=$1
kernel_prefix=${kernel_cc%gcc}
set -- "$work"/toolchains/gcc-linaro-*/bin/arm-linux-gnueabi-gcc
old_cc=$1
old_prefix=${old_cc%gcc}
runtime=$work/runtime
"$kernel_cc" --version | head -1
"$old_cc" --version | head -1
arm-linux-gnueabi-gcc --version | head -1

kmake() {
    make -j"$jobs" -C "$work/kernel" ARCH=arm CC="$kernel_cc" CROSS_COMPILE="$kernel_prefix" \
        HOSTCFLAGS=-fcommon "$@"
}

build_modules() {
    path=M7350v5_en_gpl/M7350v5_en_gpl/kernel
    tar --strip-components=2 -xf "$inputs/M7350v5_en_gpl.tar.gz" "$path"
    cp "$inputs/kernel.config" kernel/.config
    kmake olddefconfig modules_prepare
    python3 "$repo/tools/oem-module-exports.py" "$inputs" > kernel/Module.symvers
    python3 "$experiment/prepare_external.py" kernel external
    kmake M="$work/external" modules
    for module in aead authenc cbc cryptomgr esp4 hmac pcompress seqiv sha1_generic sha256_generic xfrm_algo xfrm_user; do
        find external -name "$module.ko" -exec cp '{}' "$runtime/ko" ';'
    done
    mkdir vxlan
    cp kernel/drivers/net/vxlan.c vxlan/
    printf '%s\n' 'obj-m := vxlan.o' 'ccflags-y += -DCONFIG_VXLAN_MODULE=1' > vxlan/Kbuild
    kmake M="$work/vxlan" modules
    cp vxlan/vxlan.ko "$runtime/ko"
    mkdir zx-lean
    prefix=linux-3.4-80e1fec813691ceb16567581c3fe4d49e4bab7f3/drivers/net/wireless/rtl8192cd_92es
    tar --strip-components=5 -xf "$inputs/zx-linux-3.4.tar.gz" -C zx-lean "$prefix"
    patch -d zx-lean -p1 --binary --fuzz=0 < "$zx/zx-9x07-port.patch"
    cp -a zx-lean zx-two-vap
    patch -d zx-two-vap -p1 --binary --fuzz=0 < "$zx/zx-9x07-two-vap.patch"
    python3 - <<'PY'
from pathlib import Path
import hashlib
expected = {
    'zx-lean': '556b07d89f68eaa7fd20b11d33b04eb277d1b3ba75d2d14f51442680cdbb1064',
    'zx-two-vap': '6f0c8965a0d31f19d1efa5d1af22974944ed6d344aca2f48298677a308e071f5',
}
for name, digest in expected.items():
    root = Path(name)
    tree = hashlib.sha256()
    for source in sorted(root.rglob('*')):
        if source.is_file():
            tree.update(source.relative_to(root).as_posix().encode() + b'\0')
            tree.update(hashlib.sha256(source.read_bytes()).digest())
    if tree.hexdigest() != digest:
        raise SystemExit(f'{name}: source tree differs from the retained bench tree')
    print(f'{name} source tree {digest}')
PY
    for variant in lean two-vap; do
        kmake M="$work/zx-$variant" CONFIG_PLATFORM=ARM_QUALCOMM_9x07 \
            CONFIG_RTL8192CD=m CONFIG_RTL_92E_SUPPORT=y CONFIG_POWER_SAVE=n \
            CONFIG_ZTE_TASKLET_TO_THERAD=n CONFIG_RTL_WPA3_SUPPORT=n KCFLAGS=-Os modules
        "${kernel_prefix}strip" --strip-debug --remove-section=.comment \
            -o "$runtime/ko/rtl8192es-$variant.ko" "$work/zx-$variant/rtl8192es.ko"
    done
}

build_programs() {
    mkdir userspace
    cd userspace
    for archive in musl-1.2.5.tar.gz ppp-2.4.9.tar.gz xl2tpd-v1.3.18.tar.gz; do
        tar -xf "$inputs/$archive"
    done
    ln -s "$inputs/gmp-6.3.0.tar.xz" "$inputs/strongswan-5.9.14.tar.bz2" .
    python3 "$experiment/prepare-userspace.py" .
    (
        cd ppp-ppp-2.4.9
        ./configure --prefix=/run/m7350-vpn
        make -j"$jobs" -C pppd CC="$old_cc" COPTS='-Os -march=armv7-a -mfloat-abi=soft' \
            LDFLAGS=-static CHAPMS= MPPE= USE_EAPTLS= FILTER= HAVE_MULTILINK= USE_TDB= \
            PLUGIN= HAVE_INET6= pppd
        "${old_prefix}strip" -o "$runtime/bin/pppd" pppd/pppd
    )
    (
        cd xl2tpd-1.3.18
        make -j"$jobs" CC="$old_cc" OSFLAGS=-DLINUX DFLAGS=-DTRUST_PPPD_TO_DIE LDFLAGS=-static xl2tpd
        "${old_prefix}strip" -o "$runtime/bin/xl2tpd" xl2tpd
    )
    IPSEC_WORK="$work" sh "$experiment/build-musl-staging.sh"
    for program in charon swanctl; do
        cp "musl-sources/strongswan-5.9.14/src/$program/$program" "$runtime/bin/"
    done
    "$old_cc" -Os -static -s "$experiment/live-tools/pause_oem_offload.c" \
        -o "$runtime/bin/pause_oem_offload"
    musl/bin/musl-gcc -Os -Wall -Wextra -Werror -static -s -Wl,-z,max-page-size=4096 \
        "$zx/load-module-fd.c" -o "$runtime/bin/load-module-fd-musl"
    musl/bin/musl-gcc -Os -march=armv7-a -mfloat-abi=soft -static -s "$experiment/live-tools/remove_owned_module.c" \
        -o "$runtime/bin/remove_owned_module"
    "$repo/tools/build-runtime-dropbear.sh" "$work" "$inputs" "$old_cc"
}

build_modules > "$work/modules.log" 2>&1 &
modules_pid=$!
build_programs > "$work/programs.log" 2>&1 &
programs_pid=$!
status=0
wait "$modules_pid" || { tail -60 "$work/modules.log" >&2; status=1; }
wait "$programs_pid" || { tail -60 "$work/programs.log" >&2; status=1; }
[ "$status" = 0 ] || exit "$status"
(cd "$runtime" && LC_ALL=C sha256sum bin/* ko/* > SHA256SUMS)
printf 'Built ARM runtime in %s\n' "$runtime"
