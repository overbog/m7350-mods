/* SPDX-License-Identifier: GPL-2.0-only */
#include "wifi-qr.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __linux__
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <linux/wireless.h>
#endif

static void wipe(void *data, size_t size)
{
    volatile unsigned char *p = data;
    while (size--)
        *p++ = 0;
}

/* Test fixture uses the same raw MIB bytes as the private driver ioctl. */
static int read_mib(const char *iface, const char *name, unsigned char data[128])
{
    const char *fixtures = getenv("M7350L2_WIFI_FIXTURES");
    memset(data, 0, 128);
    if (fixtures && *fixtures) {
        char path[512];
        FILE *file;
        size_t size;
        if (snprintf(path, sizeof path, "%s/%s.%s", fixtures, iface, name) >= (int)sizeof path)
            return -1;
        file = fopen(path, "rb");
        if (!file)
            return -1;
        size = fread(data, 1, 128, file);
        fclose(file);
        return size ? 0 : -1;
    }
#ifdef __linux__
    {
        struct iwreq request;
        struct ifreq flags;
        int sock, result;
        sock = socket(AF_INET, SOCK_DGRAM, 0);
        if (sock < 0)
            return -1;
        memset(&flags, 0, sizeof flags);
        snprintf(flags.ifr_name, sizeof flags.ifr_name, "%s", iface);
        if (ioctl(sock, SIOCGIFFLAGS, &flags) < 0 || !(flags.ifr_flags & IFF_UP)) {
            close(sock);
            return -1;
        }
        memset(&request, 0, sizeof request);
        snprintf(request.ifr_name, sizeof request.ifr_name, "%s", iface);
        snprintf((char *)data, 128, "%s", name);
        request.u.data.pointer = data;
        request.u.data.length = strlen(name) + 1;
        /* RTL8192CD_IOCTL_GET_MIB, identical in OEM and the ZX driver. */
        result = ioctl(sock, SIOCDEVPRIVATE + 2, &request);
        close(sock);
        if (result < 0 || request.u.data.length > 128)
            return -1;
        memset(data + request.u.data.length, 0, 128 - request.u.data.length);
        return 0;
    }
#else
    return -1;
#endif
}

static int read_number(const char *iface, const char *name, int *out)
{
    unsigned char data[128];
    if (read_mib(iface, name, data) < 0)
        return -1;
    memcpy(out, data, sizeof *out);
    return 0;
}

static char *escaped(char *dst, const char *src)
{
    while (*src) {
        if (strchr("\\;,:\"", *src))
            *dst++ = '\\';
        *dst++ = *src++;
    }
    return dst;
}

int wifi_qr_read(const char *iface, struct wifi_qr *out)
{
    unsigned char mib[128], temp[WIFI_QR_BUFFER];
    char key[64], payload[224], *end;
    size_t length;
    int opmode, psk, privacy, hidden, result = -1;
    memset(out, 0, sizeof *out);
    memset(key, 0, sizeof key);
    if (read_number(iface, "opmode", &opmode) < 0 || !(opmode & 0x10) ||
        read_number(iface, "psk_enable", &psk) < 0 ||
        read_number(iface, "encmode", &privacy) < 0 ||
        read_number(iface, "hiddenAP", &hidden) < 0 ||
        read_mib(iface, "ssid", mib) < 0)
        goto done;
    memcpy(out->ssid, mib, 32);
    if (!out->ssid[0] || (!psk && privacy))
        goto done;
    if (psk) {
        if (read_mib(iface, "passphrase", mib) < 0)
            goto done;
        memcpy(key, mib, 63);
        if (strlen(key) < 8)
            goto done;
    }
    end = payload;
    end += sprintf(end, "WIFI:T:%s;S:", psk ? "WPA" : "nopass");
    end = escaped(end, out->ssid);
    if (psk) {
        memcpy(end, ";P:", 3);
        end = escaped(end + 3, key);
    }
    if (hidden) {
        memcpy(end, ";H:true", 7);
        end += 7;
    }
    memcpy(end, ";;", 3);
    length = (size_t)(end + 2 - payload);
    memcpy(temp, payload, length);
    if (!qrcodegen_encodeBinary(temp, length, out->modules, qrcodegen_Ecc_MEDIUM,
                               1, WIFI_QR_VERSION, qrcodegen_Mask_AUTO, false)) {
        memcpy(temp, payload, length);
        if (!qrcodegen_encodeBinary(temp, length, out->modules, qrcodegen_Ecc_LOW,
                                   1, WIFI_QR_VERSION, qrcodegen_Mask_AUTO, false))
            goto done;
    }
    result = 0;
done:
    wipe(mib, sizeof mib);
    wipe(key, sizeof key);
    wipe(payload, sizeof payload);
    wipe(temp, sizeof temp);
    if (result)
        memset(out, 0, sizeof *out);
    return result;
}
