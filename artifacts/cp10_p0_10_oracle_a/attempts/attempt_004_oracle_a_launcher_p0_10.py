"""Detached P0.10 gate; intentionally exposes only `verify`."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def verify(root: Path=ROOT):
    receipt=root/'protocols/cp10_p0_10_FREEZE_RECEIPT.json'; expected='482D3EA675350BA359E66B61D381D0CA929CA7A2E02B56F5D07848C763506540'
    if hashlib.sha256(receipt.read_bytes()).hexdigest().upper()!=expected: raise RuntimeError('freeze receipt hash mismatch')
    checksum=(root/'artifacts/cp10_p0_10_FREEZE_RECEIPT.json.sha256').read_bytes()
    if checksum!=(expected+'  protocols/cp10_p0_10_FREEZE_RECEIPT.json\n').encode(): raise RuntimeError('checksum mismatch')
    def pairs(x):
        d={}
        for k,v in x:
            if k in d: raise ValueError('duplicate key')
            d[k]=v
        return d
    r=json.loads(receipt.read_text('utf8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
    for m in r['bundle_members']:
        p=root/m['path']
        if not p.is_file() or p.stat().st_size!=m['byte_length'] or hashlib.sha256(p.read_bytes()).hexdigest().upper()!=m['sha256']: raise RuntimeError('bundle mismatch '+m['path'])
    return {'status':'PASS','members':12}
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['verify']);a=p.parse_args()
    print(json.dumps(verify(),sort_keys=True))
if __name__=='__main__':main()
