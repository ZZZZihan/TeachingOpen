async (page) => {
  const evidence="/Users/xuzihan/Documents/Projects/TeachingOpen/output/playwright/showcase-five-scratch";
  await page.goto("http://127.0.0.1:18146/scratch3/player.html?workUrl=/showcase/catch-the-dots.sb3");
  await page.waitForFunction(()=>window.vm&&window.vm.runtime.targets.some(t=>t.getName()==="玩法与来源"));
  const sourceProof=await page.evaluate(async()=>{
    const url="/showcase/catch-the-dots.sb3";
    const response=await fetch(url,{cache:"no-store"});
    const bytes=await response.arrayBuffer();
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(b=>b.toString(16).padStart(2,"0")).join("");
    return {url,status:response.status,bytes:bytes.byteLength,sha256:hash};
  });
  if(sourceProof.sha256!=="1f9deec63d7074aae73f7eb430fb2e4937274446eaf68b95f8303e7e423ac1ef") throw new Error("Candidate byte hash changed");
  const read=()=>page.evaluate(()=>{
    const stage=window.vm.runtime.getTargetForStage();
    const values=Object.fromEntries(Object.values(stage.variables).map(v=>[v.name,v.value]));
    for(const name of ["剩余机会","分数","文件内最佳","生成间隔"]) values[name]=Number(values[name]);
    const controller=window.vm.runtime.targets.find(t=>t.getName()==="red3roller");
    const dots=window.vm.runtime.targets.filter(t=>["red","yellow","blue"].includes(t.getName())&&!t.isOriginal&&t.visible).map(t=>({name:t.getName(),x:t.x,y:t.y,distance:Math.hypot(t.x-controller.x,t.y-controller.y)}));
    return {values,direction:controller.direction,dots,threads:window.vm.runtime.threads.length,intro:window.vm.runtime.targets.find(t=>t.getName()==="玩法与来源").visible,endVisible:window.vm.runtime.targets.find(t=>t.getName()==="结束提示").visible};
  });
  await page.getByTitle("运行",{exact:true}).click();
  await page.waitForTimeout(150);
  const initial=await read();
  await page.keyboard.down("ArrowRight");
  await page.waitForTimeout(400);
  await page.keyboard.up("ArrowRight");
  const right=await read();
  await page.keyboard.down("ArrowLeft");
  await page.waitForTimeout(400);
  await page.keyboard.up("ArrowLeft");
  const left=await read();
  const normalize=angle=>((angle+180)%360+360)%360-180;
  if(initial.intro||initial.values["剩余机会"]!==3||initial.values["分数"]!==0||Math.abs(normalize(right.direction-initial.direction))<9||Math.abs(normalize(left.direction-right.direction))<9) throw new Error("Initial state or keyboard controls failed: "+JSON.stringify({initial,right,left}));
  let held=null;
  const transitions=[];
  let previousScore=0, previousLives=3;
  const started=Date.now();
  while(Date.now()-started<60000) {
    const state=await read();
    if(state.values["分数"]!==previousScore||state.values["剩余机会"]!==previousLives) {
      transitions.push({elapsed:Date.now()-started,...state});
      previousScore=state.values["分数"]; previousLives=state.values["剩余机会"];
    }
    if(state.threads===0) break;
    const dot=state.dots.sort((a,b)=>a.distance-b.distance)[0];
    let next=null;
    if(dot) {
      const bearing=Math.atan2(dot.x+3,dot.y-3)*180/Math.PI;
      const local={red:-60,yellow:60,blue:180}[dot.name];
      // Play normally for the first score, then deliberately choose a mismatched sector.
      const desired=normalize(bearing+90-local+(state.values["分数"]>=1?120:0));
      const difference=normalize(desired-state.direction);
      if(Math.abs(difference)>5) next=difference>0?"ArrowRight":"ArrowLeft";
    }
    if(next!==held) {
      if(held) await page.keyboard.up(held);
      held=next;
      if(held) await page.keyboard.down(held);
    }
    await page.waitForTimeout(70);
  }
  if(held) await page.keyboard.up(held);
  const ended=await read();
  if(ended.values["分数"]<1||ended.values["剩余机会"]>0||ended.threads!==0||!ended.endVisible||ended.values["文件内最佳"]!==ended.values["分数"]) throw new Error("Real scoring/game-over/high-score flow failed: "+JSON.stringify(ended));
  await page.screenshot({path:evidence+"/catch-ended.png"});
  await page.getByTitle("运行",{exact:true}).click();
  await page.waitForTimeout(100);
  const restart=await read();
  if(restart.values["剩余机会"]!==3||restart.values["分数"]!==0||restart.endVisible||restart.direction!==165) throw new Error("Restart failed");
  await page.getByTitle("停止",{exact:true}).click();
  const stopped=await read();
  if(stopped.threads!==0) throw new Error("Stop failed");
  const reopened=await page.evaluate(async()=>{
    const blob=await window.vm.saveProjectSb3(); const bytes=await blob.arrayBuffer();
    await window.vm.loadProject(bytes); window.vm.runtime.start();
    const stage=window.vm.runtime.getTargetForStage();
    return {bytes:bytes.byteLength,sourceComment:Object.values(stage.comments).some(c=>c.text.includes("Raspberry Pi Foundation")&&c.text.includes("CC BY-SA 4.0")),best:Object.values(stage.variables).find(v=>v.name==="文件内最佳").value};
  });
  await page.getByTitle("运行",{exact:true}).click();
  await page.waitForTimeout(100);
  const reopenedStarted=await read();
  await page.getByTitle("停止",{exact:true}).click();
  if(!reopened.sourceComment||reopened.best!==ended.values["文件内最佳"]||reopenedStarted.values["剩余机会"]!==3||reopenedStarted.endVisible) throw new Error("SB3 export/reopen failed");
  return {sourceProof,test:"actual player / keyboard controls / scoring / wrong-color lives / end / stop / restart / SB3 export and reopen",initial,right,left,transitions,ended,restart,stopped,reopened,reopenedStarted};
}
