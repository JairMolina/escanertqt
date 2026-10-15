import _aislamiento
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from app.services import tqt_hex
sys.modules['tqt_hex']=tqt_hex
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'station'))
import agent

class AgentVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_info_by_exact_mac_and_disconnects_without_commands(self):
        calls=[]
        device=SimpleNamespace(name='TQT_R2_V30_0069',address='AA:BB:CC:DD:EE:FF')
        class Scanner:
            @staticmethod
            async def find_device_by_address(mac,timeout):
                calls.append(('scan',mac));return device
        class Client:
            def __init__(self,d,timeout):self.device=d
            async def connect(self):calls.append(('connect',))
            async def read_gatt_char(self,char,**kwargs):
                calls.append(('read',char));return json.dumps({'boot_valid':True,'nombre':device.name}).encode()
            async def disconnect(self):calls.append(('disconnect',))
        worker=agent.BleWorker(lambda *a:None,SimpleNamespace(BleakScanner=Scanner,BleakClient=Client))
        result=await worker.verificar_r2(dict(mac=device.address,nombre=device.name))
        self.assertTrue(result['ok']);self.assertEqual(calls[0],('scan',device.address))
        self.assertEqual(calls[-1],('disconnect',));self.assertEqual(len(calls),4)
        calls.clear()
        cached=await worker.verificar_r2(dict(mac=device.address,nombre=device.name.replace('_','-')))
        self.assertTrue(cached['ok']);self.assertEqual(calls[-1],('disconnect',))
        self.assertEqual(len(calls),4,'A cached separator format must not block the authenticated INFO read')

    async def test_wrong_advertised_name_never_connects(self):
        class Scanner:
            @staticmethod
            async def find_device_by_address(*a,**k):return SimpleNamespace(name='otra R2')
        worker=agent.BleWorker(lambda *a:None,SimpleNamespace(BleakScanner=Scanner))
        with self.assertRaisesRegex(ValueError,'otro nombre'):
            await worker.verificar_r2(dict(mac='AA:BB:CC:DD:EE:FF',nombre='TQT_R2_V30_0069'))
