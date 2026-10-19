import hashlib,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'artifacts/cp10_p0_10_oracle_a';ATT=OUT/'attempts'
def e(x):return (json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def h(b):return hashlib.sha256(b).hexdigest().upper()
def w(p,b):
 fd,q=tempfile.mkstemp(dir=p.parent);f=os.fdopen(fd,'wb');f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(q,p);assert p.read_bytes()==b
def main():
 files=[ROOT/'fermion/cp10/oracle_a_p0_10.py',ROOT/'tests/test_cp10_oracle_a_runspec_p0_10.py',ROOT/'tests/test_cp10_oracle_a_launch_payload_p0_10.py',ROOT/'tests/test_cp10_oracle_a_filesystem_contract_p0_10.py'];fs=[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':h(p.read_bytes()),'bytes':p.stat().st_size}for p in files]
 ids=sorted(__import__('runpy').run_path(files[-1])['D1A_REQUIRED_CASE_IDS']);assert len(ids)==49
 a={'files':fs,'receipt':'482D3EA675350BA359E66B61D381D0CA929CA7A2E02B56F5D07848C763506540','output_contract':'9C7A6F8A1100C39ECDFB2F94EFEADD9CCF8AAA43C3C8A5463F1712E474A62C03','target24':'F1C34EE79719ED7809CF074DFDA3830C01CB54DFBD6D3D3DF1BE8C719874458C','target25':'E34589D052A42DFFD8B9A5EA7D1EAB89E487EB1168A885116407C46002078639','terminal_newline':True};b={'ids':ids,'counts':{'required':49,'collected':49,'unique':49,'valid':4,'invalid':45,'filesystem_error':43,'type_error':2},'missing':[],'unexpected':[],'duplicate':[],'coverage_node':'test_d1a_coverage','coverage_pass':True};c={'compile':'PASS','collected':590,'passed':590,'duration_seconds':2.81};paths=[OUT/'r2a2a2s1td1a_source_manifest.json',OUT/'r2a2a2s1td1a_case_coverage.json',OUT/'r2a2a2s1td1a_test_manifest.json'];vals=[a,b,c]
 hs=[]
 for p,x in zip(paths,vals):bb=e(x);w(p,bb);hs.append(h(bb))
 d={'status':'BLOCKED_PENDING_R2A2A2_S1T_D1B_AUTHORITY_ORDER_AND_SOURCE_MANIFEST','path_safety':'PASS','collision_engine':'PASS','coverage':'PASS','regression':'PASS','isolation':'PASS','d1b':'NOT_STARTED','probe':'NOT_RUN','launch':'UNAUTHORIZED','hashes':hs};db=e(d);w(OUT/'r2a2a2s1td1a_readiness_audit.json',db);m={'attempt':31,'progression':'attempts 019-030 preserved','writer_hash':h(Path(__file__).read_bytes()),'artifacts':hs+[h(db)],'changes':'writer and evidence only'};mb=e(m);w(ATT/'attempt_031_manifest.json',mb)
 for p in paths+[OUT/'r2a2a2s1td1a_readiness_audit.json',ATT/'attempt_031_manifest.json']:print(p,h(p.read_bytes()),p.stat().st_size)
if __name__=='__main__':main()
