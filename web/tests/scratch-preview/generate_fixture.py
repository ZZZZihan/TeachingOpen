"""Self-authored SVG and SB3 fixture; no remote assets."""
import hashlib, json, zipfile
from pathlib import Path
stage = '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect width="480" height="360" fill="#edf4f2"/><path d="M0 280H480" stroke="#c6d8d1" stroke-width="2"/><text x="24" y="40" fill="#244d46" font-size="22" font-family="sans-serif">Scratch save and reopen</text></svg>'
sprite = '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><circle cx="40" cy="40" r="34" fill="#dd715b"/><circle cx="30" cy="34" r="4" fill="#173f43"/><circle cx="50" cy="34" r="4" fill="#173f43"/><path d="M28 48Q40 58 52 48" fill="none" stroke="#173f43" stroke-width="3"/></svg>'
def costume(text,name,x,y):
    digest=hashlib.md5(text.encode()).hexdigest()
    return {'name':name,'assetId':digest,'dataFormat':'svg','md5ext':digest+'.svg','rotationCenterX':x,'rotationCenterY':y}
common={'variables':{},'lists':{},'broadcasts':{},'comments':{},'currentCostume':0,'sounds':[],'volume':100}
project={'targets':[dict(common,isStage=True,name='Stage',blocks={},costumes=[costume(stage,'练习背景',240,180)],layerOrder=0,tempo=60,videoTransparency=50,videoState='off',textToSpeechLanguage=None),dict(common,isStage=False,name='练习角色',blocks={},costumes=[costume(sprite,'圆形角色',40,40)],layerOrder=1,visible=True,x=0,y=0,size=100,direction=90,draggable=False,rotationStyle='all around')],'monitors':[],'extensions':[],'meta':{'semver':'3.0.0','vm':'0.2.0','agent':'TeachingOpen local self-authored fixture'}}
path=Path(__file__).with_name('sample.sb3')
with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('project.json',json.dumps(project,ensure_ascii=False))
    for text in [stage,sprite]:z.writestr(hashlib.md5(text.encode()).hexdigest()+'.svg',text)
