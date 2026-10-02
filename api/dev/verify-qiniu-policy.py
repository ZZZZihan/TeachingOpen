#!/usr/bin/env python3
"""Run offline Qiniu policy assertions from the exact backend JAR, without cloud access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--jar',required=True,type=Path);p.add_argument('--java-home',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='teaching-qiniu-policy-') as directory:
 root=Path(directory)
 with zipfile.ZipFile(a.jar) as jar:
  for name in jar.namelist():
   if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
    (root/Path(name).name).write_bytes(jar.read(name))
   elif name=='BOOT-INF/classes/org/jeecg/modules/common/util/QiniuUploadPolicy.class':
    out=root/'org/jeecg/modules/common/util/QiniuUploadPolicy.class';out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(jar.read(name))
 cp=str(root)+':'+str(root)+'/*'
 subprocess.run([str(a.java_home/'bin/javac'),'-cp',cp,'-d',str(root),str(Path(__file__).with_name('VerifyQiniuOwnership.java'))],check=True,capture_output=True)
 output=subprocess.check_output([str(a.java_home/'bin/java'),'-cp',cp,'VerifyQiniuOwnership'],text=True)
 cases=[{'case':line[5:],'passed':True} for line in output.splitlines() if line.startswith('PASS ')]
 a.output.parent.mkdir(parents=True,exist_ok=True)
 a.output.write_text(json.dumps({'observed_utc':datetime.now(timezone.utc).isoformat(),'jar_sha256':hashlib.sha256(a.jar.read_bytes()).hexdigest(),'scope':'offline generated policy and rejected keys; no cloud upload/stat/delete executed','passed':len(cases),'total':len(cases),'cases':cases},indent=2)+'\n')
 print(output)
