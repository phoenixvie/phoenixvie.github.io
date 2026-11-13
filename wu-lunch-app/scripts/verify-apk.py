import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / 'android/app/build/outputs/apk/release'
apk = folder / 'app-release.apk'
generated = (root / 'src/previewHtml.ts').read_text(encoding='utf-8')
design = re.search(r'export const designHash = "([a-f0-9]+)"', generated).group(1)
with zipfile.ZipFile(apk) as archive:
    bundle = archive.read('assets/index.android.bundle')
    assert design.encode() in bundle, 'APK does not contain the current bundled design'
config = json.loads((root / 'app.json').read_text())['expo']
version = config['version']
version_code = config['android']['versionCode']
sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
aapt = sorted(sdk.glob('build-tools/*/aapt'))[-1]
badging = subprocess.check_output([str(aapt), 'dump', 'badging', str(apk)], text=True)
assert f"versionCode='{version_code}'" in badging, 'APK has the wrong version code'
assert f"versionName='{version}'" in badging, 'APK has the wrong version name'
assert "name='at.startit.wulunch'" in badging, 'APK has the wrong application id'
target = folder / f'WU-Food-{version}.apk'
target.write_bytes(apk.read_bytes())
info = {'version': version, 'versionCode': version_code, 'commit': os.environ.get('GITHUB_SHA'), 'designSha256': design, 'apkSha256': hashlib.sha256(target.read_bytes()).hexdigest()}
(folder / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
print(json.dumps(info))
