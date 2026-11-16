#!/usr/bin/env python3
"""Prepare ONLY an offline experimental Kbuild tree. Never invokes a compiler/device."""
import argparse,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('kernel',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists():raise SystemExit('Output must not exist; preserve previous experiments')
root=a.kernel.resolve();out=a.output.resolve();out.mkdir(parents=True)
# Preserve local source-relative headers by copying the crypto directory; Kbuild
# compiles only the explicit list below. No vendor files are modified.
shutil.copytree(root/'crypto',out/'crypto',ignore=shutil.ignore_patterns('*.o','.*.cmd','*.ko'))
crypto=['aead','pcompress','authenc','hmac','cbc','sha1_generic','sha256_generic','md5','des_generic','seqiv']
(out/'crypto'/'Kbuild').write_text('obj-m += '+' '.join(x+'.o' for x in crypto)+' cryptomgr.o\ncryptomgr-y := algboss.o testmgr.o\n')
for sub,files in [('xfrm',['xfrm_algo','xfrm_user']),('ipv4',['esp4'])]:
 d=out/sub;d.mkdir()
 for f in files:shutil.copyfile(root/'net'/sub/(f+'.c'),d/(f+'.c'))
 (d/'Kbuild').write_text('obj-m += '+' '.join(f+'.o' for f in files)+'\n')
(out/'Kbuild').write_text('obj-m += crypto/ xfrm/ ipv4/\n')
manifest={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
(out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Prepared experimental source tree:',out)
print('Not compiled; dependency closure, exports and ABI remain unvalidated.')
