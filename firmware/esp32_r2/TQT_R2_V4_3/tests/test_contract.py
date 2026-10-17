"""Contract and legacy-source checks; complements real native crypto tests."""
import json
import re
import unittest
from pathlib import Path

FW = Path(__file__).resolve().parents[1]
REPO = FW.parents[2]


class FirmwareOfflineContract(unittest.TestCase):
    def test_wire_layout_matches_normative_contract(self):
        contract = json.loads((REPO / 'protocols/offline-v1.json').read_text())
        header = (FW / 'tqt_offline_wire.h').read_text()
        constants = {k: int(v) for k, v in re.findall(r'\b([A-Z_]+)\s*=\s*(\d+)', header)}
        for field, symbol in {
            'grant_uuid': 'UUID', 'device_public_key': 'DEVICE_KEY',
            'phone_public_key': 'PHONE_KEY', 'image_iv': 'IV',
            'source_counter_le32': 'COUNTER', 'source_app_digest': 'SOURCE_DIGEST',
            'transfer_sha256': 'TRANSFER_DIGEST', 'target_app_digest': 'TARGET_DIGEST',
            'image_bytes_le32': 'IMAGE_BYTES', 'name_ascii_nul': 'NAME',
            'hardware_ascii_nul': 'HARDWARE', 'firmware_ascii_nul': 'FIRMWARE',
            'mac': 'MAC', 'anchor_key_id': 'ANCHOR',
            'server_signature_raw_rs': 'SERVER_SIG',
            'phone_session_signature_raw_rs': 'PHONE_SIG',
        }.items():
            self.assertEqual(constants[symbol], contract['fields'][field][0], field)
        self.assertEqual(constants['BODY_BYTES'], contract['grant_body_bytes'])
        self.assertEqual(constants['GRANT_BYTES'], contract['grant_bytes'])
        self.assertEqual(constants['SESSION_BYTES'], contract['session_manifest_bytes'])
        self.assertEqual(constants['INFO_BYTES'], contract['info_transport']['offline_info_bytes'])
        magic = re.search(r'MAGIC\[16\]="([^"]+)"', header)[1].encode().ljust(16, b'\0')
        self.assertEqual(magic.hex(), contract['magic_ascii_hex'])
        for label, value in contract['labels'].items():
            self.assertIn(f'{label.upper()}_LABEL[]="{value}"', header)

    def test_hardware_and_profile_legacy_compatibility(self):
        old = FW.parent / 'TQT_R2_V4_2'
        legacy = (old / 'TQT_R2_V4_2.ino').read_text()
        expected = legacy.replace('FIRMWARE: V4.2 - NOMBRE EXACTO Y OTA BLE RAPIDA',
                                  'FIRMWARE: V4.3 - OTA BLE ONLINE Y OFFLINE P256')
        self.assertEqual((FW / 'TQT_R2_V4_3.ino').read_text(), expected)
        self.assertIn('#define ENABLE_VDD_SDIO_3V3_EFUSE_FIX 0', expected)
        for name in ('tqt_profile.h', 'tqt_ota.h'):
            self.assertEqual((FW / name).read_bytes(), (old / name).read_bytes())
        self.assertEqual((FW / 'tqt_profile.cpp').read_text(),
                         (old / 'tqt_profile.cpp').read_text().replace('"4.2"', '"4.3"'))
        self.assertEqual((FW / 'enrollment_trust.h').read_bytes(),
                         (FW.parent / 'TQT_R2_BASE_V4_0_GENERIC/enrollment_trust.h').read_bytes())

    def test_any_commit_consumes_before_selecting_boot_partition(self):
        ota = (FW / 'tqt_ota.cpp').read_text()
        commit = ota.split('if(command==2)', 1)[1].split('if(tqtOtaBusy()', 1)[0]
        self.assertLess(commit.index('tqtOfflineConsume('), commit.index('esp_ota_set_boot_partition('))
        self.assertIn('counter_persist_failed', commit)
        self.assertIn('offlineSession?offlineManifest+TqtOfflineWire::UUID:nullptr', commit)
        self.assertIn('bootHealthy&&tqtOfflineAvailable()', ota)

    def test_legacy_info_fits_gatt_attribute(self):
        # Maximum canonical profile lengths, uint32 partition, 500B data chunk.
        info = dict(nombre='N'*23, hw='9'*7, fw='9'*15, mac='ff:ff:ff:ff:ff:ff',
                    ota_protocol=1, key_id='f'*16, nonce='f'*32, app_sha256='f'*64,
                    proof='f'*64, boot_valid=False, partition=4294967295, chunk=500,
                    name_format=2)
        self.assertLessEqual(len(json.dumps(info, separators=(',', ':')).encode()), 512)
        ota = (FW / 'tqt_ota.cpp').read_text()
        self.assertIn('d45a0006-6a76-4e41-9f38-a7043f0ec069', ota)
        self.assertNotIn('tqtOfflineInfoJson', ota)


if __name__ == '__main__':
    unittest.main()
