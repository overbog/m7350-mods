/* Session check for the m7350l2 CGI. Uses the OEM libauth exactly like
 * web_cgi: verifyIpOrToken(REMOTE_ADDR, token) == 0 means authorised.
 * The token is read from stdin (not argv) so it never shows in ps.
 * Exit 0 = authorised, 1 = rejected, 2 = usage. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int verifyIpOrToken(const char *ip, const char *token);

int main(void)
{
    char token[64];
    const char *ip = getenv("REMOTE_ADDR");
    size_t n;

    if (!fgets(token, sizeof token, stdin))
        return 1;
    n = strcspn(token, "\r\n");
    token[n] = '\0';
    /* verifyIpOrToken(NULL, NULL) returns 0 (OEM public path): never allow
     * an empty address or token through. */
    if (!ip || !*ip || n == 0 || n >= sizeof token - 1)
        return 1;
    return verifyIpOrToken(ip, token) == 0 ? 0 : 1;
}
