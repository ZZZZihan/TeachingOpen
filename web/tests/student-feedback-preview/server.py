"""Loopback-only read-only feedback fixtures; no API proxy, auth or persistent changes."""
import argparse,json,time
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--directory',type=Path,required=True);args=parser.parse_args()
cases=[
('zero','零分也有具体反馈',0,'这次提交还没有实验记录，暂记 0 分。\n请补充观察结果与判断依据。','2'),
('string-zero','零分，无评语','0','','2'),
('comment','只有评语，不伪装评分',None,'你的思路很清楚。\n请补充数据来源，继续完善下一稿。','2'),
('pending','已提交，尚未评分',None,None,'1'),
('score','已经评分，暂无评语',5,None,'2'),
('long','长中文反馈与多段落',3,('观察记录完整，但还需要解释变化的原因。请结合课程所学逐项分析。'*35)+'\n\n下一步：\n1. 先列出假设。\n2. 用实验排除其他原因。','2'),
('token','连续字符与长链接反馈',4,'请检查以下标识：\n'+'RESULT_'+('ABCDEF0123456789'*60)+'\nhttps://example.invalid/'+('longsegment'*35),'2'),
('html','评语中的标签保持纯文本',2,'<script>window.feedbackExecuted=true</script>\n<img src=x onerror=alert(1)>\n这些字符是教师反馈文字，应直接显示。','2'),
('blank','空白评语，未评分',None,' \n\t ','0'),
('normal','简短的成熟反馈',4,'记录完整、结构清楚。下次请补充实验中的失败尝试。','2')]
rows=[]
for key,name,score,comment,status in cases:
    rows.append({'id':'feedback-'+key,'workName':name,'workType':'0','workType_dictText':'文件作品','workStatus':status,'workStatus_dictText':{'0':'草稿','1':'待批改','2':'已批改'}[status],'viewNum':2,'starNum':1,'workTag':'','coverFileKey_url':'','createTime':'2026-10-05 10:00:00','workFileKey_url':'/fixtures/readonly.txt','score':score,'teacherComment':comment})
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(args.directory),**kw)
    def log_message(self,*a):pass
    def send_json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        url=urlsplit(self.path)
        if url.path=='/teaching/teachingWork/getWorkTags':return self.send_json({'success':True,'result':['观察记录','课程作业']})
        if url.path=='/teaching/teachingWork/mine':
            q=parse_qs(url.query);name=q.get('workName',[''])[0];found=[row for row in rows if name in row['workName']];page=int(q.get('pageNo',['1'])[0]);size=int(q.get('pageSize',['10'])[0]);return self.send_json({'success':True,'result':{'records':found[(page-1)*size:page*size],'total':len(found)}})
        if url.path.startswith('/teaching/'):return self.send_json({'success':False,'message':'合成只读服务不修改数据'},403)
        return super().do_GET()
    def do_POST(self):return self.send_json({'success':False,'message':'合成只读服务不修改数据'},403)
    def do_DELETE(self):return self.send_json({'success':False,'message':'合成只读服务不修改数据'},403)
print(f'Feedback synthetic preview: http://127.0.0.1:{args.port}/?view=list and /?view=center',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
