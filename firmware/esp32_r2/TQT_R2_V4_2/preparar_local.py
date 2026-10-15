"""Prepare a private Arduino sketch for offline compilation; stdlib only."""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
from pathlib import Path


def prepare(project, store, nombre=None, hw=None, fw=None, identity_file=None):
    project=Path(project).resolve();store=Path(store).resolve()
    profile=(project/'tqt_profile.cpp').read_text(encoding='utf-8')
    pattern=r'"TQT_R2_CFG_V1",\s*2,\s*"([0-9.]+)",\s*"([0-9.]+)",\s*"([A-Z0-9_-]+)",\s*"ESP32-WROOM-32E-N4",\s*1,\s*\{0\}'
    match=re.search(pattern,profile)
    if not match:raise ValueError('Usa el proyecto plantilla, sin una clave privada escrita en sus fuentes.')
    hw=hw or match[1];fw=fw or match[2];nombre=nombre or match[3]
    if not re.fullmatch(r'\d+(?:\.\d+)+',hw) or len(hw)>7:raise ValueError('HW invalido.')
    if not re.fullmatch(r'\d+(?:\.\d+)+',fw) or len(fw)>15 or tuple(map(int,fw.split('.')))<(4,0):raise ValueError('FW OTA invalido.')
    if not re.fullmatch(re.escape('TQT-R2-V'+hw.replace('.','')+'-')+r'\d{4}',nombre) or nombre.endswith('-0000') or len(nombre)>23:
        raise ValueError('Indica el nombre exacto, por ejemplo TQT-R2-V30-0067; debe coincidir con HW.')
    if len(list(project.glob('*.ino')))!=1:raise ValueError('Se requiere un solo sketch Arduino.')
    sketch=next(project.glob('*.ino')).stem
    identity=Path(identity_file).resolve() if identity_file else store/'identidades'/(nombre+'.json')
    created=False
    if identity.exists():
        data=json.loads(identity.read_text(encoding='utf-8-sig'))
        if data.get('nombre')!=nombre or data.get('hw')!=hw:raise ValueError('La credencial pertenece a otra tarjeta o HW.')
        key=bytes.fromhex(data.get('ota_key',''))
        if len(key)!=32 or not any(key):raise ValueError('Credencial OTA invalida.')
    else:
        if identity_file:raise ValueError('No existe el archivo de identidad indicado; no se sustituyo la clave.')
        key=secrets.token_bytes(32)
        data=dict(schema=1,nombre=nombre,hw=hw,ota_key=key.hex(),origin='offline',web_registered=False)
        identity.parent.mkdir(parents=True,exist_ok=True)
        # Never replace a credential another invocation may have just created.
        with os.fdopen(os.open(identity,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as out:
            json.dump(data,out,indent=2)
        created=True
    # Stable sketch path keeps the compiler cache reusable between units.
    work=store/'proyectos'/sketch
    work.mkdir(parents=True,exist_ok=True)
    for item in project.iterdir():
        if item.is_file() and item.suffix.lower() in ('.ino','.cpp','.h','.ps1'):
            shutil.copyfile(item,work/item.name)
    values=', '.join('0x%02x'%b for b in key)
    initializer='"TQT_R2_CFG_V1", 2, '+json.dumps(hw)+', '+json.dumps(fw)+', '+json.dumps(nombre)+', "ESP32-WROOM-32E-N4", 1, {'+values+'}'
    (work/'tqt_profile.cpp').write_text(profile[:match.start()]+initializer+profile[match.end():],encoding='utf-8')
    return dict(project=str(work),identity_file=str(identity),nombre=nombre,hw=hw,fw=fw,
                key_id=hashlib.sha256(key).hexdigest()[:16],new_identity=created,
                web_registered=bool(data.get('web_registered',False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',default=str(Path(__file__).resolve().parent))
    default_store=Path.home()/'.tqt/R2'
    p.add_argument('--store',default=str(default_store))
    p.add_argument('--nombre');p.add_argument('--hw');p.add_argument('--fw');p.add_argument('--identity-file')
    a=p.parse_args()
    print(json.dumps(prepare(a.project,a.store,a.nombre,a.hw,a.fw,a.identity_file),ensure_ascii=False))
