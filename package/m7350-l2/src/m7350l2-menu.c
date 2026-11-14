/* OLED menu for the M7350 mode switcher.
 *
 * Idle: subscribed to key_detect; does nothing until MENU (key_detect "wps")
 * is held. Then: hold the oledd start script, stop oledd, draw on the
 * 128x128 RGB565 framebuffer, MENU short = next item, POWER short = confirm,
 * 15 s idle = leave unchanged. Leaving releases the script and starts oledd.
 * Reset is never used.
 *
 * Found on the device:
 *  - state_ctrl runs /etc/init.d/start_oledd start on a key press when oledd
 *    is not running, so a plain stop is undone and oledd draws over the menu.
 *    While the menu is open a no-op script is bind-mounted over that path.
 *  - Freezing oledd instead blocks key_detect, which sends every key to
 *    oledd synchronously: presses arrive late and holds turn into taps.
 * If any oledd appears anyway, the menu aborts with no action, so a choice
 * can never be confirmed on a screen the user cannot see.
 *
 * Protocol (docs/wan-backup-l2tp-ui-design.md): register with a 40-byte
 * datagram [0x2a, type, socket path] to /tmp/key_detect.sock; events arrive
 * as text such as "key_detect: wps long press".
 *
 * Every path and command can be overridden by environment for host tests.
 */
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "font8x14.h"
#include "wifi-qr.h"

#define FB_W 128
#define FB_H 128
#define FB_STRIDE 256
#define FB_SIZE (FB_STRIDE * FB_H)
#define GLYPH_W 8
#define GLYPH_H 14
#define IDLE_SECS 15
#define WHITE 0xffff
#define BLACK 0x0000

static const char *env(const char *name, const char *fallback)
{
    const char *v = getenv(name);
    return v && *v ? v : fallback;
}

/* The s90319fb SPI panel does not refresh from memory writes alone: after
 * drawing, cmd_oled and oledd push a region with this custom ioctl, taking
 * {x, y, w, h} as four ints (found by disassembling cmd_oled). */
#define FBIO_S90319_FLUSH 0x4619

static unsigned short *fb;
static int fbfd = -1;

static void flush(void)
{
    int rect[4] = { 0, 0, FB_W, FB_H };
    if (fbfd >= 0)
        ioctl(fbfd, FBIO_S90319_FLUSH, rect);  /* fails harmlessly on a host test file */
}

static void clear(void)
{
    memset(fb, 0, FB_SIZE);
}

static void fill(int x, int y, int w, int h, unsigned short c)
{
    int i, j;
    for (j = y; j < y + h && j < FB_H; j++)
        for (i = x; i < x + w && i < FB_W; i++)
            fb[j * (FB_STRIDE / 2) + i] = c;
}

static void text(int x, int y, const char *s, unsigned short fg)
{
    for (; *s && x + GLYPH_W <= FB_W; s++, x += GLYPH_W) {
        unsigned char c = (unsigned char)*s;
        int r, b;
        if (c < 32 || c > 126)
            c = '?';
        for (r = 0; r < GLYPH_H; r++)
            for (b = 0; b < GLYPH_W; b++)
                if (font8x14[c - 32][r] & (0x80 >> b))
                    fb[(y + r) * (FB_STRIDE / 2) + x + b] = fg;
    }
}

static const char *modes[] = { "factory", "vpn" };
enum menu_item { OEM, VPN, WIFI_QR, EXIT, ITEMS };
static const char *labels[] = { "OEM", "VPN", "Wi-Fi QR", "Exit" };

static int mode_index(const char *m)
{
    int i;
    for (i = 0; i < WIFI_QR; i++)
        if (!strcmp(m, modes[i]))
            return i;
    return -1;
}

/* Reads "key=value" from `m7350-mode status`. */
static void status_value(const char *key, char *out, size_t len)
{
    char cmd[300], line[200];
    size_t k = strlen(key);
    FILE *p;
    snprintf(cmd, sizeof cmd, "%s status 2>/dev/null",
             env("M7350L2_MODE", "/data/m7350-l2/bin/m7350-mode"));
    out[0] = '\0';
    if (!(p = popen(cmd, "r")))
        return;
    while (fgets(line, sizeof line, p))
        if (!strncmp(line, key, k) && line[k] == '=') {
            snprintf(out, len, "%s", line + k + 1);
            out[strcspn(out, "\n")] = '\0';
        }
    pclose(p);
}

static void draw_menu(int sel, int active)
{
    int i, y;
    clear();
    text(4, 2, "VPN MODES", WHITE);
    fill(0, 18, FB_W, 1, WHITE);
    for (i = 0; i < ITEMS; i++) {
        y = 22 + i * 18;
        if (i == sel) {
            fill(0, y - 2, FB_W, GLYPH_H + 3, WHITE);
            text(2, y, labels[i], BLACK);
        } else {
            text(2, y, labels[i], WHITE);
        }
        if (i == active)
            fill(FB_W - 6, y + 4, 4, 4, i == sel ? BLACK : WHITE);
    }
    fill(0, FB_H - 18, FB_W, 1, WHITE);
    text(0, FB_H - 15, "MENU:next PWR:OK", WHITE);
    flush();
}

static void draw_message(const char *l1, const char *l2, const char *l3, const char *l4)
{
    clear();
    text(0, 22, l1, WHITE);
    if (l2) text(0, 42, l2, WHITE);
    if (l3) text(0, 62, l3, WHITE);
    if (l4) text(0, 82, l4, WHITE);
    flush();
}

static void draw_switch_failure(const char *reason)
{
    char line[FB_W / GLYPH_W + 1];
    int y;
    clear();
    text(0, 0, "Switch failed:", WHITE);
    if (!*reason)
        reason = "See web page";
    for (y = 18; *reason && y <= 98; y += 16) {
        size_t n = strcspn(reason, "\n");
        if (n >= sizeof line)
            n = sizeof line - 1;
        memcpy(line, reason, n);
        line[n] = '\0';
        text(0, y, line, WHITE);
        reason += n;
        if (*reason == '\n')
            reason++;
    }
    text(0, 114, "See web page", WHITE);
    flush();
}

static void logmsg(const char *what)
{
    FILE *f = fopen(env("M7350L2_LOG", "/run/m7350-l2/menu.log"), "a");
    struct timespec ts;
    if (!f)
        return;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    fprintf(f, "%ld.%03ld %s\n", (long)ts.tv_sec, ts.tv_nsec / 1000000, what);
    fclose(f);
}

/* oledd processes: from M7350L2_OLEDD_PIDS_CMD (host tests) or /proc. */
static int list_oledd(int *pids, int max)
{
    const char *cmd = getenv("M7350L2_OLEDD_PIDS_CMD");
    int n = 0;
    if (cmd && *cmd) {
        FILE *p = popen(cmd, "r");
        int v;
        if (!p)
            return 0;
        while (n < max && fscanf(p, "%d", &v) == 1)
            pids[n++] = v;
        pclose(p);
        return n;
    } else {
        DIR *d = opendir("/proc");
        struct dirent *e;
        char path[sizeof e->d_name + sizeof "/proc//comm"], comm[32];
        if (!d)
            return 0;
        while (n < max && (e = readdir(d))) {
            FILE *f;
            if (!isdigit((unsigned char)e->d_name[0]))
                continue;
            snprintf(path, sizeof path, "/proc/%s/comm", e->d_name);
            if (!(f = fopen(path, "r")))
                continue;
            if (fgets(comm, sizeof comm, f) && !strcmp(comm, "oledd\n"))
                pids[n++] = atoi(e->d_name);
            fclose(f);
        }
        closedir(d);
        return n;
    }
}

/* True when an oledd we did not freeze is running: the screen was taken. */
static int screen_taken(const int *frozen, int nfrozen)
{
    int now[16], n, i, j, known;
    if (!frozen)
        return 0;
    n = list_oledd(now, 16);
    for (i = 0; i < n; i++) {
        for (known = 0, j = 0; j < nfrozen; j++)
            known |= now[i] == frozen[j];
        if (!known)
            return 1;
    }
    return 0;
}

enum key_action { KEY_NEXT = 1, KEY_CONFIRM, KEY_OPEN };

/* While the menu owns the screen, check for an OEM takeover every second. */
static int wait_key(int sock, int secs, const int *frozen, int nfrozen)
{
    char buf[128];
    time_t until = time(NULL) + secs;
    for (;;) {
        fd_set r;
        struct timeval tv;
        ssize_t n;
        int ready;
        long left = (long)(until - time(NULL));
        if (screen_taken(frozen, nfrozen))
            return -2;
        if (left <= 0)
            return 0;
        FD_ZERO(&r);
        FD_SET(sock, &r);
        tv.tv_sec = frozen && left > 1 ? 1 : left;
        tv.tv_usec = 0;
        ready = select(sock + 1, &r, NULL, NULL, &tv);
        if (ready < 0)
            return errno == EINTR ? 0 : -1;
        if (ready == 0)
            continue;
        n = recv(sock, buf, sizeof buf - 1, 0);
        if (n < 0)
            return errno == EINTR ? 0 : -1;
        buf[n] = '\0';
        buf[strcspn(buf, "\r\n")] = '\0';
        logmsg(buf);
        if (screen_taken(frozen, nfrozen))
            return -2;
        if (frozen) {
            if (strstr(buf, "wps short press"))
                return KEY_NEXT;
            if (strstr(buf, "power short press"))
                return KEY_CONFIRM;
        } else if (strstr(buf, "wps long press")) {
            return KEY_OPEN;
        }
    }
}

static void drain(int sock)
{
    char buf[128];
    while (recv(sock, buf, sizeof buf, MSG_DONTWAIT) > 0)
        ;
}

static int run(const char *cmd)
{
    int rc = system(cmd);
    return rc == -1 ? -1 : WEXITSTATUS(rc);
}

#define OLEDD_INIT "/etc/init.d/start_oledd"
#define HOLD_SCRIPT "/run/m7350-l2/oledd-hold"

/* Bind a no-op over the oledd start script so state_ctrl cannot restart it. */
static int hold_oledd(void)
{
    FILE *f;
    if (getenv("M7350L2_OLEDD_HOLD"))
        return run(getenv("M7350L2_OLEDD_HOLD"));
    mkdir("/run/m7350-l2", 0755);
    if (!(f = fopen(HOLD_SCRIPT, "w")))
        return -1;
    fputs("#!/bin/sh\nexit 0\n", f);
    fclose(f);
    chmod(HOLD_SCRIPT, 0755);
    return run("mount -o bind " HOLD_SCRIPT " " OLEDD_INIT " >/dev/null 2>&1");
}

static int oledd_held(void)
{
    if (getenv("M7350L2_OLEDD_HELD"))
        return run(getenv("M7350L2_OLEDD_HELD")) == 0;
    return run("grep -q ' " OLEDD_INIT " ' /proc/self/mountinfo") == 0;
}

/* Release the start script and bring oledd back. Safe to call repeatedly. */
static void release_oledd(void)
{
    int i;
    if (getenv("M7350L2_OLEDD_RELEASE"))
        run(getenv("M7350L2_OLEDD_RELEASE"));
    else
        for (i = 0; i < 3 && oledd_held(); i++)
            run("umount " OLEDD_INIT " >/dev/null 2>&1");
    {
        int one[1];
        if (list_oledd(one, 1) == 0)
            run(env("M7350L2_OLEDD_START", OLEDD_INIT " start >/dev/null 2>&1"));
    }
}

static int open_screen(void)
{
    fbfd = open(env("M7350L2_FB", "/dev/fb0"), O_RDWR);
    if (fbfd < 0)
        return -1;
    fb = mmap(NULL, FB_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fbfd, 0);
    if (fb == MAP_FAILED) {
        close(fbfd);
        fbfd = -1;
        return -1;
    }
    return 0;
}

static void close_screen(void)
{
    munmap(fb, FB_SIZE);
    close(fbfd);
    fbfd = -1;
}

/* An OEM startup can leave its logo on the panel after the daemon exits. */
static void show_vpn_status_if_needed(void)
{
    int pid[1];
    char active[32];

    status_value("active", active, sizeof active);
    if (strcmp(active, "vpn") && strcmp(active, "home") && strcmp(active, "provider"))
        return;
    sleep(1);
    if (list_oledd(pid, 1) != 0 || open_screen() != 0)
        return;
    draw_message("VPN active", NULL, "Hold MENU", NULL);
    close_screen();
    logmsg("oledd unavailable; drew VPN status");
}

static void text_center(int y, const char *s, unsigned short fg)
{
    int w = (int)strlen(s) * GLYPH_W;
    text(w < FB_W ? (FB_W - w) / 2 : 0, y, s, fg);
}

/* QR in the middle, the key hint on the top line (under the MENU button,
 * which sits above the middle of the screen) and the SSID on the bottom line.
 * The scale leaves a 2-module quiet zone between the code and each text line
 * (version 3 = 29 modules: scale 3, 87 px, 6 px gaps). */
static void draw_qr(const struct wifi_qr *qr, const char *hint)
{
    int x, y, size = qrcodegen_getSize(qr->modules);
    int scale = (FB_H - 2 * GLYPH_H) / (size + 4);
    int origin;
    char name[FB_W / GLYPH_W + 1];

    if (scale < 1)
        scale = 1;
    origin = (FB_W - size * scale) / 2;
    /* OLED: inverted code (light modules on black), so only the dark modules
     * of a normal code are lit. Current phone cameras read inverted codes. */
    clear();
    for (y = 0; y < size; y++)
        for (x = 0; x < size; x++)
            if (qrcodegen_getModule(qr->modules, x, y))
                fill(origin + x * scale, origin + y * scale, scale, scale, WHITE);
    text_center(0, hint, WHITE);
    /* 16 characters fit; a longer SSID ends in '~'. */
    snprintf(name, sizeof name, "%.*s", (int)(sizeof name - 1), qr->ssid);
    if (strlen(qr->ssid) > sizeof name - 1)
        name[sizeof name - 2] = '~';
    text_center(FB_H - GLYPH_H, name, WHITE);
    flush();
}

static int show_wifi_qr(int sock, int active)
{
    const char *ifaces[] = { "wlan0", "wlan0-va1", "wlan0", "wlan0-va0" };
    struct wifi_qr qr;
    int available[3], count = 0, selected = 0, key = 0, i, none[1];

    if (access("/sys/class/net/bridge3/brif/wlan0-va0", F_OK) == 0) {
        ifaces[1] = "wlan0-va0";
        ifaces[3] = NULL;
    }
    /* Only the physical OEM AP or the active interfaces of VPN mode. */
    if (active == OEM || active == VPN)
        for (i = active == OEM ? 0 : 1; i < (active == OEM ? 1 : 4); i++)
            if (ifaces[i] && wifi_qr_read(ifaces[i], &qr) == 0)
                available[count++] = i;
    if (!count) {
        draw_message("Wi-Fi QR", "No available AP", NULL, NULL);
        key = wait_key(sock, 4, none, 0);
        goto done;
    }
    /* Straight to the first QR; MENU shows the next network's QR, POWER or
     * 30 s without keys closes. With one network MENU closes too. */
    for (;;) {
        if (wifi_qr_read(ifaces[available[selected]], &qr) < 0)
            break;
        draw_qr(&qr, count > 1 ? "next" : "exit");
        key = wait_key(sock, 30, none, 0);
        if (key != KEY_NEXT || count == 1)
            break;
        selected = (selected + 1) % count;
    }
done:
    memset(&qr, 0, sizeof qr);
    return key;
}

static void menu(int sock)
{
    char active_s[32], cmd[300], err[200];
    int active, sel, key, i, none[1];

    status_value("active", active_s, sizeof active_s);
    active = mode_index(active_s);
    if (!strcmp(active_s, "home") || !strcmp(active_s, "provider"))
        active = 1;
    if (active_s[0] && strcmp(active_s, "dirty") && active < 0)
        return;
    /* Take the screen: hold the start script first, then stop oledd. */
    if (hold_oledd() != 0) {
        logmsg("could not hold the oledd start script; menu not opened");
        return;
    }
    run(env("M7350L2_OLEDD_STOP", "start-stop-daemon -K -n oledd >/dev/null 2>&1"));
    for (i = 0; i < 30 && list_oledd(none, 1) > 0; i++)
        usleep(100000);
    if (list_oledd(none, 1) > 0) {
        logmsg("oledd did not stop; menu not opened");
        release_oledd();
        return;
    }
    run(env("M7350L2_PANEL_ON", "/usr/bin/cmd_oled -o >/dev/null 2>&1"));
    if (open_screen() != 0) {
        release_oledd();
        return;
    }
    sel = active >= 0 ? active : 0;
    draw_menu(sel, active);
    logmsg("menu open");
    /* No oledd may run while the menu is shown: any that appears means the
     * screen was taken (wait_key returns -2). */
    while ((key = wait_key(sock, IDLE_SECS, none, 0)) == KEY_NEXT) {
        sel = (sel + 1) % ITEMS;
        draw_menu(sel, active);
    }
    if (key == -2) {
        /* Someone else owns the screen now: do nothing, leave it to them. */
        logmsg("screen taken by another oledd; aborted without action");
        close_screen();
        drain(sock);
        release_oledd();
        return;
    }
    logmsg(key == KEY_CONFIRM ? "menu confirm" : "menu timeout");
    if (key == KEY_CONFIRM && sel == WIFI_QR)
        key = show_wifi_qr(sock, active);
    else if (key == KEY_CONFIRM && sel < WIFI_QR && sel != active) {
        draw_message("Switching to", labels[sel], "please wait...", NULL);
        snprintf(cmd, sizeof cmd, "%s set %s >/dev/null 2>&1",
                 env("M7350L2_MODE", "/data/m7350-l2/bin/m7350-mode"), modes[sel]);
        if (run(cmd) == 0) {
            draw_message("Active:", labels[sel], NULL, NULL);
        } else {
            status_value("last_error", err, sizeof err);
            draw_switch_failure(err);
        }
        sleep(4);
    }
    if (key != -2) {
        clear();
        flush();
    }
    close_screen();
    drain(sock);
    release_oledd();
    if (key != -2)
        show_vpn_status_if_needed();
    logmsg("menu closed; oledd released");
}

int main(void)
{
    struct sockaddr_un me, kd;
    unsigned char reg[40];
    const char *path = env("M7350L2_SOCK", "/tmp/m7350l2-menu.sock");
    int sock, key;

    signal(SIGPIPE, SIG_IGN);
    /* A previous instance died with the start script held: restore oledd. */
    if (oledd_held()) {
        logmsg("stale oledd hold found at start; releasing");
        release_oledd();
    }
    if (strlen(path) > 31) {
        fprintf(stderr, "socket path longer than key_detect accepts\n");
        return 2;
    }
    sock = socket(AF_UNIX, SOCK_DGRAM, 0);
    memset(&me, 0, sizeof me);
    me.sun_family = AF_UNIX;
    strncpy(me.sun_path, path, sizeof me.sun_path - 1);
    unlink(path);
    if (sock < 0 || bind(sock, (struct sockaddr *)&me, sizeof me) < 0) {
        perror("bind");
        return 1;
    }
    chmod(path, 0600);
    memset(reg, 0, sizeof reg);
    reg[0] = 0x2a;
    reg[1] = 0; /* all events; filtered by text below */
    memcpy(reg + 2, path, strlen(path));
    memset(&kd, 0, sizeof kd);
    kd.sun_family = AF_UNIX;
    strncpy(kd.sun_path, env("M7350L2_KEYSOCK", "/tmp/key_detect.sock"), sizeof kd.sun_path - 1);
    if (sendto(sock, reg, sizeof reg, 0, (struct sockaddr *)&kd, sizeof kd) != (ssize_t)sizeof reg) {
        perror("register");
        return 1;
    }
    show_vpn_status_if_needed();
    for (;;) {
        key = wait_key(sock, 3600, NULL, 0);
        if (key < 0)
            return 1;
        if (key == KEY_OPEN)
            menu(sock);
    }
}
