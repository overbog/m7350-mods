#!/usr/bin/env python3
"""Build the web overlay: OEM /WEBSERVER/www copy plus the VPN page.

usage: build-www.py <oem-www-dir> <package-dir> <out-dir>
Every patch must match exactly once in the OEM 181220 files; otherwise the
build stops and nothing is produced.
"""
import hashlib
import shutil
import sys
from pathlib import Path

oem, pkg, final = (Path(p) for p in sys.argv[1:4])
if final.exists():
    sys.exit('output exists: %s' % final)
out = final.parent / (final.name + '.full')
shutil.rmtree(out, ignore_errors=True)
shutil.copytree(oem, out, symlinks=True)


def replace_once(text, old, new, what):
    if text.count(old) != 1:
        sys.exit('patch %s: expected 1 match, found %d' % (what, text.count(old)))
    return text.replace(old, new)


js_path = out / 'settings.min.js'
original = js_path.read_bytes()
js = original.decode('utf-8')

# 1. Use the same Advanced submenu structure as Wireless and Device.
vpn_pages = [
    ("M7350VPNMode", "m7350l2", "Operating Mode"),
    ("M7350VPNProfiles", "m7350VpnProfiles", "VPN Profiles"),
    ("M7350VPNWifi", "m7350VpnWifi", "Wi-Fi Settings"),
]
vpn_submenu = ','.join(f'{{id:"{key}"}}' for key, _, _ in vpn_pages)
js = replace_once(js, '{header:"PowerSaving"},{header:"Device",',
                  '{header:"PowerSaving"},' + f'{{header:"M7350VPN",sub:[{vpn_submenu}]}},'
                  + '{header:"Device",', 'menu')

# 2. Keep the existing VPN URL and shift Device from menu index 7 to 8.
start = js.index('SoftwareUpdate:{pages:["softwareUpdate"],index:[7,0]}')
end = js.index('DeviceInfo:{pages:["deviceInfo"],index:[7,6]}') + len('DeviceInfo:{pages:["deviceInfo"],index:[7,6]}')
device = js[start:end]
if device.count('index:[7,') != 7:
    sys.exit('patch device indices: unexpected layout')
vpn_routes = 'M7350VPN:{pages:["m7350l2"],index:[7,0]},' + ''.join(
    f'{key}:{{pages:["{page}"],index:[7,{index}]}},'
    for index, (key, page, _) in enumerate(vpn_pages)
)
js = js[:start] + vpn_routes + device.replace('index:[7,', 'index:[8,') + js[end:]

# Keep OEM log types on their original API. VPN reads the system syslog buffer.
js = replace_once(js, 'Settings.sysLog={onLoad:function(){k=!0,b(),j()}',
                  'Settings.sysLog={onLoad:function(){Settings.m7350VpnLog.preselect(),k=!0,b(),j()}',
                  'VPN log deep link')
js = replace_once(js, 'function c(b){if(k)return k=!1,m.getMdLog(),f(),void 0;',
                  'function c(b){if(k)return k=!1,m.getMdLog(),f(),void 0;'
                  'if(Settings.m7350VpnLog.page(b,r,o))return;', 'VPN log pagination')
js = replace_once(js, 'function f(){a("#tableSysLog td").empty(),m.refresh()}',
                  'function f(){if(Settings.m7350VpnLog.page(1,r,o))return;'
                  'a("#tableSysLog td").empty(),m.refresh()}', 'VPN log refresh')
js = replace_once(js, 'function d(){var b=m.get("logList");',
                  'function d(){if(Settings.m7350VpnLog.selected())return;var b=m.get("logList");',
                  'VPN log response guard')
log_page = out / 'advHTML' / 'sysLog.html'
log_page.write_text(replace_once(log_page.read_text(), '<option value="6">OTHER</option>',
                   '<option value="6">OTHER</option>\n                <option value="7">VPN</option>', 'VPN log type'))

# 3. Page module.
js += '\n' + (pkg / 'www' / 'm7350l2.js').read_text()
# Mount after the OEM Status template has been inserted.
js = replace_once(js, 'H.loadHTML("tabHTML/"+d.toLowerCase()+".html",function(a){e(d,a)})',
                  'H.loadHTML("tabHTML/"+d.toLowerCase()+".html",function(a){e(d,a);'
                  'if(d==="Status")Settings.m7350VpnStatus()})',
                  'VPN status card mount')
js = replace_once(js, 'a.i18n.switchFont(),H[c[d]].onLoad()',
                  'a.i18n.switchFont(),H[c[d]].onLoad();'
                  'if(c[d]==="clientList")Settings.m7350VpnClients()', 'VPN online clients mount')
# Version the changed assets so an already authenticated tab can reload them.
layout = (pkg / 'www' / 'm7350l2.css').read_bytes()
revision = hashlib.sha256(js.encode() + log_page.read_bytes() + layout + b''.join(
    (pkg / 'www' / 'advHTML' / (page + '.html')).read_bytes()
    for _, page, _ in vpn_pages)).hexdigest()[:12]
js = replace_once(js, 'H.loadHTML(d,function(b){e[g]=b,',
                  'H.loadHTML(d+(/^(m7350|sysLog$)/.test(g)?"?v=' + revision + '":""),'
                  'function(b){e[g]=b,', 'versioned templates')
js_path.write_text(js)
entry = out / 'settings.html'
settings = replace_once(entry.read_text(), 'src="settings.min.js"',
                        f'src="settings.min.js?v={revision}"', 'versioned settings script')
settings = replace_once(settings, 'href="tpweb.css"', f'href="tpweb.css?v={revision}"',
                        'versioned settings stylesheet')
mobile_viewport = r"""<script>
    (function () {
        var viewport = document.createElement("meta");
        viewport.name = "viewport";
        viewport.content = "width=device-width, initial-scale=1";
        function updateViewport() {
            var route = location.hash;
            if (route === "#Status" || /^#Advanced\/M7350VPN(?:\/|$)/.test(route)) {
                if (!viewport.parentNode) document.head.appendChild(viewport);
            } else if (viewport.parentNode) {
                viewport.parentNode.removeChild(viewport);
            }
        }
        updateViewport();
        window.addEventListener("hashchange", updateViewport);
    })();
    </script>"""
settings = replace_once(settings, '<meta charset="UTF-8">',
                        '<meta charset="UTF-8">\n    ' + mobile_viewport, 'mobile VPN and Status viewport')
entry.write_text(settings)

login = out / 'login.html'
login.write_text(replace_once(login.read_text(), '<h4 id="statusLbl"></h4>',
    '<h4 id="statusLbl"></h4>\n'
    '                <div class="content-group hide" id="m7350-login-mode">\n'
    '                    <label class="content-label">Operating Mode:</label>\n'
    '                    <label id="m7350-login-mode-value"></label>\n'
    '                </div>\n'
    '                <p class="hide" id="m7350-login-switch" role="status"></p>', 'login mode row'))
login.write_text(replace_once(login.read_text(), '<script src="login.min.js"></script>',
    '<script src="login.min.js"></script>\n'
    '    <script>\n' + (pkg / 'www' / 'm7350-login-mode.js').read_text() +
    '    </script>', 'login mode request'))

# 4. Draw a lock with its own color and dimensions, independent of the OEM sprite.
from urllib.parse import quote

css_path = out / 'tpweb.css'
lock = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#36444a" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="5" y="10" width="14" height="11" rx="2"/>'
        '<path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/></svg>')
css = css_path.read_text(encoding='utf-8')
css_path.write_text(css + '\n#M7350VPNLink .icon-M7350VPN,#M7350VPNLink .icon-M7350VPN-selected,'
                    '#m7350VpnStatus .icon-M7350VPN{'
                    'width:24px;height:24px;background-position:center;'
                    'background-size:22px 22px;background-image:url("data:image/svg+xml,'
                    + quote(lock, safe='') + '")}\n' + layout.decode(), encoding='utf-8')

# 5. Menu label.
for lang in ('en', 'cn'):
    props = out / 'i18n' / ('str_%s.properties' % lang)
    text = props.read_text(encoding='utf-8')
    if 'M7350VPN' in text:
        sys.exit('label already present in %s' % props)
    labels = ['M7350VPN = VPN'] + [f'{key} = {label}' for key, _, label in vpn_pages]
    props.write_text(text.rstrip('\n') + '\n' + '\n'.join(labels) + '\n', encoding='utf-8')

# 6. Page and CGI.
for _, page, _ in vpn_pages:
    filename = page + '.html'
    shutil.copy(pkg / 'www' / 'advHTML' / filename, out / 'advHTML' / filename)
cgi = out / 'cgi-bin' / 'm7350l2'
shutil.copy(pkg / 'www' / 'cgi-bin' / 'm7350l2', cgi)
cgi.chmod(0o755)

# 7. Keep only what changed: /data is small. The boot hook bind-mounts each
# entry of www.mounts over the same path in the OEM web root.
MOUNTS = ['settings.html', 'login.html', 'settings.min.js', 'tpweb.css', 'i18n/str_en.properties',
          'i18n/str_cn.properties', 'advHTML', 'cgi-bin']
final.mkdir()
for rel in MOUNTS:
    src, dst = out / rel, final / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst)
shutil.rmtree(out)
(final.parent / 'www.mounts').write_text('\n'.join(MOUNTS) + '\n')

# The boot hook mounts the overlay only over this exact OEM file.
(final.parent / 'www.oem-settings.sha256').write_text(hashlib.sha256(original).hexdigest() + '\n')
print('overlay built:', final)
