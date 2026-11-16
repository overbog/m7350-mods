/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <unistd.h>

/* The staging GCC 4.9.2 sysroot predates this ARM EABI syscall. */
#if !defined(SYS_finit_module) && defined(__arm__) && defined(__ARM_EABI__)
#define SYS_finit_module 379
#endif

int main(int argc, char **argv)
{
    int fd;

    if (argc != 2) {
        fputs("usage: load-module-fd MODULE.ko\n", stderr);
        return 2;
    }

    fd = open(argv[1], O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        perror("open module");
        return 1;
    }

    if (syscall(SYS_finit_module, fd, "", 0) < 0) {
        perror("finit_module");
        close(fd);
        return 1;
    }

    close(fd);
    return 0;
}
