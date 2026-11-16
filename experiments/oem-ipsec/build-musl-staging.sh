#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Alternative to glibc static binaries, which can still dlopen OEM NSS libraries.
set -eu
work=${IPSEC_WORK:-/srv/research/ipsec-build}
src=$work/userspace
export CC=arm-linux-gnueabi-gcc AR=arm-linux-gnueabi-ar RANLIB=arm-linux-gnueabi-ranlib
export CFLAGS='-Os -march=armv7-a -mfloat-abi=soft -Wno-error=incompatible-pointer-types'
if [ ! -e "$src/musl/bin/musl-gcc" ]; then
 cd "$src/musl-1.2.5"
 ./configure --target=arm-linux-gnueabi --prefix="$src/musl" --disable-shared > ../musl-configure.log 2>&1
 make -j2 > ../musl-build.log 2>&1
 make install > ../musl-install.log 2>&1
fi
for headers in linux asm asm-generic; do
 cp -R "/usr/arm-linux-gnueabi/include/$headers" "$src/musl/include/"
done
export CC=$src/musl/bin/musl-gcc
mkdir -p "$src/musl-sources"
cd "$src/musl-sources"
if [ ! -d gmp-6.3.0 ]; then tar -xf ../gmp-6.3.0.tar.xz; fi
if [ ! -d strongswan-5.9.14 ]; then tar -xf ../strongswan-5.9.14.tar.bz2; fi
cd gmp-6.3.0
./configure --host=arm-linux-gnueabi --prefix="$src/deps-musl" --disable-shared --enable-static > ../../gmp-musl-configure.log 2>&1
make -j2 > ../../gmp-musl-build.log 2>&1
make install > ../../gmp-musl-install.log 2>&1
cd ../strongswan-5.9.14
./configure --host=arm-linux-gnueabi --prefix=/run/m7350-vpn --sysconfdir=/run/m7350-vpn/etc --with-piddir=/run/m7350-vpn \
 --disable-defaults --disable-shared --enable-static --enable-monolithic \
 --enable-charon --enable-ikev1 --enable-vici --enable-swanctl \
 --enable-kernel-netlink --enable-socket-default --enable-random --enable-nonce \
 --enable-aes --enable-sha1 --enable-sha2 --enable-hmac --enable-kdf --enable-gmp \
 CPPFLAGS="-I$src/deps-musl/include" LDFLAGS="-static -L$src/deps-musl/lib" \
 > ../../strongswan-musl-configure.log 2>&1
make -j2 > ../../strongswan-musl-build.log 2>&1
rm -f src/charon/charon src/swanctl/swanctl
make -C src/charon LDFLAGS="-all-static -L$src/deps-musl/lib" >> ../../strongswan-musl-build.log 2>&1
make -C src/swanctl LDFLAGS="-all-static -L$src/deps-musl/lib" >> ../../strongswan-musl-build.log 2>&1
arm-linux-gnueabi-strip src/charon/charon src/swanctl/swanctl
file src/charon/charon src/swanctl/swanctl
sha256sum src/charon/charon src/swanctl/swanctl
