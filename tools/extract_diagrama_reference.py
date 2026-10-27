"""Extract the supplied standalone reference; never execute its HTML/JavaScript."""
import argparse
import base64
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.current = [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.current = [dict(attrs), []]

    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.scripts.append((self.current[0], ''.join(self.current[1])))
            self.current = None


def extract(source, root):
    raw = source.read_bytes()
    parser = Scripts()
    parser.feed(raw.decode('utf-8-sig'))
    blocks = {attrs.get('id'): text for attrs, text in parser.scripts if attrs.get('id')}
    data = json.loads(blocks['tqt-diagram-data'])
    images = json.loads(blocks['tqt-diagram-assets'])
    assert {k: len(v) for k, v in data['wires'].items()} == {'20': 19, '30': 18}
    assert {g['id'] for g in data['groups']} == {'power', 'gps', 'r3', 'motor', 'm1', 'm2'}
    for wires in data['wires'].values():
        assert len({w['id'] for w in wires}) == len(wires)
        assert all(w['groupId'] in {g['id'] for g in data['groups']} for w in wires)
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    data['provenance'] = dict(source_file=source.name, html_sha256=hashlib.sha256(raw).hexdigest(),
                              data_sha256=hashlib.sha256(canonical).hexdigest())
    data['assets'], asset_hashes = {'pages': {}, 'overview': {}}, {}
    dest = root/'app/static/img/diagrama_tqt'
    dest.mkdir(parents=True, exist_ok=True)
    for kind, keys in [('pages', ['2', '3', '5', '6']), ('overview', ['20', '30'])]:
        assert set(images[kind]) == set(keys)
        for key in keys:
            prefix, encoded = images[kind][key].split(',', 1)
            assert prefix == 'data:image/jpeg;base64'
            payload = base64.b64decode(encoded, validate=True)
            assert payload.startswith(b'\xff\xd8') and payload.endswith(b'\xff\xd9')
            name = f'{kind}_{key}.jpg'
            (dest/name).write_bytes(payload)
            data['assets'][kind][key] = '/static/img/diagrama_tqt/'+name
            asset_hashes[name] = hashlib.sha256(payload).hexdigest()
    data['provenance']['asset_sha256'] = asset_hashes
    catalog = root/'app/static/catalogos/diagrama_tqt.json'
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    # Reuse only the pure, escaped SVG renderer, not the standalone application's shell.
    code = next(text for attrs, text in parser.scripts if not attrs.get('type') and 'function renderHarnessSVG' in text)
    renderer = code[code.index('function renderHarnessSVG'):code.index('const root=')].strip()
    assert renderer.endswith('}')
    assert not any(token in renderer for token in ('fetch(', 'eval(', 'localStorage', 'document.', 'window.'))
    renderer = renderer.replace('font-family:Inter,Arial,sans-serif', 'font-family:var(--font-ui,Arial,sans-serif)')
    (root/'app/static/js/diagrama_svg.js').write_text(
        '/* Pure SVG reading layout adapted from the supplied Diagrama_TQT.html. */\n'
        "(function(){'use strict';\n"+renderer+'\nwindow.TQTDiagramSVG=renderHarnessSVG;\n})();\n', encoding='utf-8')
    print(json.dumps(dict(points={k: len(v) for k, v in data['wires'].items()},
                          assets=len(asset_hashes), source_sha256=data['provenance']['html_sha256'])))


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('source', type=Path)
    opts = args.parse_args()
    extract(opts.source, Path(__file__).resolve().parents[1])
