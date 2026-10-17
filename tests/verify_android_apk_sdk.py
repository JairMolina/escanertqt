"""Real SDK verification of a DEBUG fixture, never approval of a production release.

Run from repository root: python tests/verify_android_apk_sdk.py --sdk SDK_DIRECTORY
Uses a temporary folder outside Git, no signing keys and no running server/database.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services import android_ota


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--build-tools', default='36.1.0')
    args = parser.parse_args()
    tools = args.sdk.resolve() / 'build-tools' / args.build_tools
    signer = tools / ('apksigner.bat' if os.name == 'nt' else 'apksigner')
    aapt = tools / ('aapt.exe' if os.name == 'nt' else 'aapt')
    source = ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk'
    certificate = subprocess.run([str(signer), 'verify', '--print-certs', str(source)], check=True, capture_output=True, text=True).stdout
    digest = re.search(r'Signer #1 certificate SHA-256 digest: ([a-fA-F0-9]{64})', certificate)[1].lower()
    with tempfile.TemporaryDirectory(prefix='tqt-apk-qa-') as temporary:
        directory = Path(temporary)
        apk = directory / 'TQT-QA.apk'
        shutil.copyfile(source, apk)
        meta = dict(approved=True, filename=apk.name, package_name='com.tqt.ota', version_code=1,
                    version_name='0.1.0', min_sdk=26, certificate_sha256=digest,
                    sha256=hashlib.sha256(apk.read_bytes()).hexdigest())
        (directory / 'manifest.json').write_text(json.dumps(meta), encoding='utf-8')
        os.environ.update(TQT_ANDROID_APK_DIR=str(directory), TQT_ANDROID_APKSIGNER=str(signer), TQT_ANDROID_AAPT=str(aapt))
        public, raw = android_ota.apk_package()
        assert public['available'] and raw == apk.read_bytes()
        unsigned = ROOT / 'android/app/build/outputs/apk/release/app-release-unsigned.apk'
        shutil.copyfile(unsigned, apk)
        meta['sha256'] = hashlib.sha256(apk.read_bytes()).hexdigest()
        (directory / 'manifest.json').write_text(json.dumps(meta), encoding='utf-8')
        try:
            android_ota.apk_package()
        except android_ota.AndroidError as error:
            assert error.status == 503
        else:
            raise AssertionError('Unsigned release must be rejected by the real SDK')
    print(json.dumps(dict(debug_fixture_verified=True, unsigned_release_rejected=True,
                          production_release=False, sha256=public['sha256'], certificate_sha256=digest)))


if __name__ == '__main__':
    main()
