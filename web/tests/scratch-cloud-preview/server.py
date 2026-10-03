"""Temporary loopback preview using the candidate's exact existing API proxy."""
import argparse,importlib.util,sys
from pathlib import Path
from http.server import ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('--backend-dev',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);p.add_argument('--port',type=int,default=18133);a=p.parse_args()
sys.path.insert(0,str(a.backend_dev.resolve()))
from local_runtime import load_ports,assert_database
assert_database(a.runtime)
spec=importlib.util.spec_from_file_location('preview_proxy',a.backend_dev/'serve-frontend.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.LocalFrontend.ports=dict(load_ports(a.runtime),frontend=a.port)
server=ThreadingHTTPServer(('127.0.0.1',a.port),lambda *args,**kw:module.LocalFrontend(*args,directory=str(a.directory.resolve()),**kw))
print('Synthetic preview at 127.0.0.1:'+str(a.port),flush=True);server.serve_forever()
