// Exact shipped provider with Node WebSocket and a VM-interface harness. Credentials only on stdin.
const {create}=require('../public/scratch3/cloud-client.js')
;(async()=>{
 let raw='';for await(const chunk of process.stdin)raw+=chunk;const args=JSON.parse(raw)
 if(new URL(args.origin).hostname!=='127.0.0.1'||!args.publicId.startsWith('fixture_cloud_client_'))throw Error('Synthetic localhost only')
 const clients=[],cases=[];const sleep=ms=>new Promise(r=>setTimeout(r,ms));const wait=async fn=>{for(let i=0;i<100;i++){if(fn())return;await sleep(50)}throw Error('Condition timeout')};const check=(name,passed)=>{cases.push({case:name,passed:!!passed});if(!passed)throw Error(name)}
 function client(token,seed=false,project=args.publicId){
  const h={token,states:[],variables:{score:{name:'score',value:'local',isCloud:true}},connections:0}
  const vm={runtime:{hasCloudData:()=>true,getTargetForStage:()=>({variables:h.variables})},setCloudProvider:p=>h.provider=p,postIOData:(device,data)=>{const variable=Object.values(h.variables).find(v=>v.name===data.varUpdate.name);if(variable)variable.value=data.varUpdate.value}}
  class Observed extends WebSocket{constructor(url){super(url);h.connections++;h.socket=this}}
  h.api=create({vm,origin:args.origin,WebSocket:Observed,getToken:()=>h.token,seed,onStatus:s=>h.states.push(s)});h.state=()=>h.states.at(-1);clients.push(h);h.api.bind(project);return h
 }
 try{
  const owner=client(args.ownerToken),second=client(args.ownerToken),anonymous=client('')
  await wait(()=>[owner,second,anonymous].every(h=>['ready','readonly'].includes(h.state()?.phase)))
  check('shipped client reads real Redis snapshot on owner and anonymous sockets',[owner,second,anonymous].every(h=>h.variables.score.value==='41'))
  owner.api.updateVariable('score',42);await wait(()=>[owner,second,anonymous].every(h=>h.variables.score.value==='42'))
  check('owner update reaches both tabs and anonymous reader',true)
  check('anonymous update rejected locally',anonymous.api.updateVariable('score',999)===false)
  second.api.destroy();owner.api.updateVariable('score',43);await wait(()=>anonymous.variables.score.value==='43');check('closing one tab preserves others',true)
  const denied=client(args.otherToken,false,args.privateId);await wait(()=>denied.state()?.phase==='denied');await sleep(700);check('private work denial stops reconnect storm',denied.connections===1)
  const seeded=client(args.ownerToken,true,args.seedId);seeded.variables.created={name:'created',value:'7',isCloud:true};await wait(()=>seeded.state()?.phase==='ready');await sleep(300)
  const seedReader=client(args.ownerToken,false,args.seedId);seedReader.variables.created={name:'created',value:'0',isCloud:true};await wait(()=>seedReader.variables.created.value==='7');check('saved editor seeds missing definition in real Redis',true)
  owner.api.bind(args.privateId);await wait(()=>owner.variables.score.value==='99');check('switch project reads new authorized snapshot',owner.connections===2)
  const peer=client(args.otherToken);await wait(()=>peer.state()?.phase==='ready');peer.api.updateVariable('score',44);await wait(()=>anonymous.variables.score.value==='44');check('old project cannot update switched client',owner.variables.score.value==='99')
  peer.api.updateVariable('score',45);await wait(()=>anonymous.variables.score.value==='45');check('authorized public participant updates existing value',true)
  peer.token='';peer.api.checkSession();await sleep(100);check('local logout closes and clears pending connection',peer.state()?.phase==='session'&&peer.socket.readyState>=2)
  const response=await fetch(args.origin+'/api/sys/logout',{headers:{'X-Access-Token':args.ownerToken}});check('synthetic owner session revoked through real API',response.ok)
  owner.api.updateVariable('score',100);await wait(()=>owner.state()?.phase==='denied');await sleep(600);check('server logout policy closes client without automatic reconnect',owner.connections===2)
 }finally{for(const h of clients)h.api.destroy()}
 process.stdout.write(JSON.stringify({cases,passed:cases.filter(c=>c.passed).length,total:cases.length,scope:'Shipped provider with Node native WebSocket, actual Java/Redis/MySQL; VM interface harness, not authenticated browser.'}))
})().catch(()=>{process.stderr.write('Live cloud client check failed; no credential output.\n');process.exitCode=1})
