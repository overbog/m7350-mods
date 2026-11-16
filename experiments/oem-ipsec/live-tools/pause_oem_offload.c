/* SPDX-License-Identifier: GPL-2.0-only */
/* GPL-2.0. Explicit, non-forcing pause of the OEM shortcut connection manager.
 * This is an authorized network-policy operation, not research-module cleanup.
 * Save the original module first; restore with insmod only during rollback.
 */
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/syscall.h>
int main(void)
{
 if(syscall(SYS_delete_module,"shortcut_fe_cm",O_NONBLOCK)!=0){
  perror("pause shortcut_fe_cm");return 1;
 }
 puts("Paused OEM shortcut_fe_cm; verify absence in /proc/modules");
 return 0;
}
