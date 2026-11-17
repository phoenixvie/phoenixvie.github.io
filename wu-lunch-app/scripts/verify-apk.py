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
assert "name='at.startit.wufood'" in badging, 'APK has the wrong application id'
# Nur die Internet-Berechtigung (plus die interne von Android); keine ungenutzten Berechtigungen der Vorlage.
permissions = set(re.findall(r"uses-permission: name='([^']+)'", badging))
allowed = {'android.permission.INTERNET', 'at.startit.wufood.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'}
assert permissions <= allowed, f'APK requests unexpected permissions: {sorted(permissions - allowed)}'
assert 'android.permission.INTERNET' in permissions
# Signatur: Mit Upload-Schlüssel darf weder APK noch App-Bundle mit dem öffentlichen Debug-Schlüssel signiert sein.
apksigner = sorted(sdk.glob('build-tools/*/apksigner'))[-1]
apk_cert = subprocess.check_output([str(apksigner), 'verify', '--print-certs', str(apk)], text=True)
upload_signed = os.environ.get('EXPECT_UPLOAD_SIGNATURE') == 'true'
assert ('CN=Android Debug' in apk_cert) != upload_signed, 'APK signature does not match the expected key'
cert_sha = re.search(r'certificate SHA-256 digest: ([0-9a-f]+)', apk_cert).group(1)
target = folder / f'WU-Food-{version}.apk'
target.write_bytes(apk.read_bytes())
info = {'version': version, 'versionCode': version_code, 'commit': os.environ.get('GITHUB_SHA'), 'designSha256': design, 'apkSha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'signingCertSha256': cert_sha, 'signedWith': 'upload-key' if upload_signed else 'debug-key'}
if upload_signed:
    bundle_file = root / 'android/app/build/outputs/bundle/release/app-release.aab'
    with zipfile.ZipFile(bundle_file) as archive:
        assert design.encode() in archive.read('base/assets/index.android.bundle'), 'App bundle does not contain the current design'
    aab_cert = subprocess.check_output(['keytool', '-printcert', '-jarfile', str(bundle_file)], text=True)
    assert 'CN=Android Debug' not in aab_cert and 'SHA256:' in aab_cert, 'App bundle is not signed with the upload key'
    assert cert_sha.upper() in aab_cert.replace(':', '').upper(), 'APK and App bundle are signed with different keys'
    aab_target = folder / f'WU-Food-{version}.aab'
    aab_target.write_bytes(bundle_file.read_bytes())
    info['aabSha256'] = hashlib.sha256(aab_target.read_bytes()).hexdigest()
(folder / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
print(json.dumps(info))
