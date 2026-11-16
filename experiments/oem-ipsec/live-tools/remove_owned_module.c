/* SPDX-License-Identifier: GPL-2.0-only */
/* GPL-2.0. Non-forcing cleanup of explicitly named research modules only. */
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <fcntl.h>
int main(int argc,char **argv)
{
 const char *allowed[]={"m7350_crypto_diag","cbc","hmac","sha1_generic","sha256_generic","cryptomgr","pcompress","aead","authenc","seqiv","xfrm_algo","xfrm_user","esp4","vxlan","ip6_udp_tunnel","udp_tunnel",NULL};
 int i,ok=0;
 if(argc!=2)return 2;
 for(i=0;allowed[i];i++)if(!strcmp(argv[1],allowed[i]))ok=1;
 if(!ok)return 2;
 if(syscall(SYS_delete_module,argv[1],O_NONBLOCK)!=0){int e=errno;fprintf(stderr,"delete_module: errno=%d (%s)\n",e,strerror(e));return 1;}
 puts("delete_module returned success; verify /proc/modules separately");return 0;
}
