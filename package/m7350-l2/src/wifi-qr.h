/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef M7350_WIFI_QR_H
#define M7350_WIFI_QR_H
#include "qrcodegen/qrcodegen.h"
#define WIFI_QR_VERSION 9
#define WIFI_QR_BUFFER qrcodegen_BUFFER_LEN_FOR_VERSION(WIFI_QR_VERSION)
struct wifi_qr {
    uint8_t modules[WIFI_QR_BUFFER];
    char ssid[33];
};
/* Reads only an active AP. Credentials are never returned or logged. */
int wifi_qr_read(const char *iface, struct wifi_qr *out);
#endif
