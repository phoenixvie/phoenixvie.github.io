import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / 'android/app/build/outputs/apk/release'
apk = folder / 'app-release.apk'
generated = (root / 'src/previewHtml.ts').read_text(encoding='utf-8')
design = re.search(r'export const designHash = "([a-f0-9]+)"', generated).group(1)
with zipfile.ZipFile(apk) as archive:
    bundle = archive.read('assets/index.android.bundle')
    assert design.encode() in bundle, 'APK does not contain the current bundled design'
target = folder / 'WU-Food-0.3.0.apk'
target.write_bytes(apk.read_bytes())
info = {'version': '0.3.0', 'commit': os.environ.get('GITHUB_SHA'), 'designSha256': design, 'apkSha256': hashlib.sha256(target.read_bytes()).hexdigest()}
(folder / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
print(json.dumps(info))
