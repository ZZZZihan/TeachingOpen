"""Generate an original empty one-page SJR; no user/student material."""
import hashlib, json, struct, zlib, zipfile
from pathlib import Path

def chunk(tag, payload):
    return struct.pack('!I', len(payload))+tag+payload+struct.pack('!I', zlib.crc32(tag+payload)&0xffffffff)
width,height=192,144
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+bytes([240,246,244])*width)*height))+chunk(b'IEND',b'')
thumbnail=hashlib.md5(png).hexdigest()+'.png'
project={'name':'ScratchJr 练习 & 100%','version':'iOSv01','deleted':'NO','mtime':'0','isgift':'0',
'json':{'pages':['page 1'],'currentPage':'page 1','page 1':{'textstartat':36,'sprites':[],'num':1,'layers':[]}},
 'thumbnail':{'pagecount':1,'md5':thumbnail},'id':'teachingopen-self-authored-fixture'}
with zipfile.ZipFile(Path(__file__).with_name('sample.sjr'),'w',zipfile.ZIP_DEFLATED) as archive:
    for name,data in [('project/data.json',json.dumps(project,ensure_ascii=False).encode()),('project/thumbnails/'+thumbnail,png)]:
        entry=zipfile.ZipInfo(name,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(entry,data)
