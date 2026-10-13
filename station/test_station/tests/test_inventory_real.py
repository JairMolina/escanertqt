import tempfile
import unittest
from pathlib import Path
from tqtstation.reporting import load_inventory, compare_inventory


class InventoryNamesTests(unittest.TestCase):
    def _records(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'inventario.csv'
            file.write_text('ID,MAC_R1,MAC_R2,Nombre,Observaciones\n'
                            '1,AA:BB:CC:DD:EE:01,AA:BB:CC:DD:FF:01,TQT_R1_V3_0_0001,Ejemplo\n'
                            '2,8c:8c:29:c3:d7:fe,8c:8c:29:c3:f4:86,TQT-R1-V30-0036,\n')
            return load_inventory(file)

    def test_actual_inventory_row_id_two_matches_hardware_0036(self):
        recs=self._records()
        found=compare_inventory(recs,'0036','8c:8c:29:c3:d7:fe','8C:8C:29:C3:D7:FE',
                                '8C:8C:29:C3:F4:86','8C:8C:29:C3:F4:86')
        self.assertEqual(found['state'],'coincide', found)
        self.assertEqual(found['matched_by'],'nombre')
        self.assertEqual(found['csv_id'],'2')

    def test_wrong_ble_mac_not_approved(self):
        recs=self._records()
        found=compare_inventory(recs,'0036','8c:8c:29:c3:d7:fe','8C:8C:29:C3:D7:00',
                                '8C:8C:29:C3:F4:86','8C:8C:29:C3:F4:86')
        self.assertEqual(found['state'],'no_coincide')

    def test_duplicate_hardware_names_prevent_approval(self):
        recs=self._records()
        recs['3']=dict(recs['2'])
        result=compare_inventory(recs,'0036','8c:8c:29:c3:d7:fe','8c:8c:29:c3:d7:fe',
                                 '8c:8c:29:c3:f4:86','8c:8c:29:c3:f4:86')
        self.assertEqual(result['state'],'ambiguo')

    def test_csv_id_conflicts_with_name_prevents_approval(self):
        recs=self._records()
        recs['36']=dict(recs['1'])
        result=compare_inventory(recs,'0036','8c:8c:29:c3:d7:fe','8c:8c:29:c3:d7:fe',
                                 '8c:8c:29:c3:f4:86','8c:8c:29:c3:f4:86')
        self.assertEqual(result['state'],'ambiguo')

if __name__=='__main__': unittest.main()
