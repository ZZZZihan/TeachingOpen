async (page) => {
  const evidence = "/Users/xuzihan/Documents/Projects/TeachingOpen/output/playwright/showcase-five-scratch";
  await page.goto("http://127.0.0.1:18146/scratch3/player.html?workUrl=/showcase/boat-race.sb3");
  await page.waitForFunction(()=>window.vm&&window.vm.runtime.targets.some(t=>t.getName()==="玩法与来源"));
  const sourceProof=await page.evaluate(async()=>{
    const url="/showcase/boat-race.sb3";
    const response=await fetch(url,{cache:"no-store"});
    const bytes=await response.arrayBuffer();
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(b=>b.toString(16).padStart(2,"0")).join("");
    return {url,status:response.status,bytes:bytes.byteLength,sha256:hash};
  });
  if(sourceProof.sha256!=="79cea250da8ff1c3241b2d67801a08da04662e8a2c912a528ce700e07ea52d7b") throw new Error("Candidate byte hash changed");
  const canvas = page.locator("canvas").first();
  const rect = await canvas.boundingBox();
  const xy = (x,y) => ({x:rect.x+(x+240)/480*rect.width, y:rect.y+(180-y)/360*rect.height});
  await page.getByTitle("运行", {exact:true}).click();
  let pos = xy(-190,-150);
  await page.mouse.move(pos.x,pos.y);
  await page.waitForTimeout(200);
  const start = await page.evaluate(() => {
    const t = window.vm.runtime.targets.find(t=>t.getName()==="boat");
    return {boat:{x:t.x,y:t.y,costume:t.currentCostume}, intro:window.vm.runtime.targets.find(t=>t.getName()==="玩法与来源").visible, threads:window.vm.runtime.threads.length};
  });
  pos=xy(-100,-150);
  await page.mouse.move(pos.x,pos.y);
  const samples=[];
  for(let i=0;i<140;i++) {
    samples.push(await page.evaluate(() => {
      const t=window.vm.runtime.targets.find(t=>t.getName()==="boat");
      return {x:t.x,y:t.y,costume:t.currentCostume};
    }));
    await page.waitForTimeout(25);
  }
  const hit = samples.find(t=>t.costume===1);
  const reset = samples.find((t,i)=>i>samples.findIndex(t=>t.costume===1)&&t.costume===0&&t.x<-185);
  if(!hit||!reset||start.intro) throw new Error("Boat collision/reset or intro hide failed");
  await page.getByTitle("停止", {exact:true}).click();
  const readStop=()=>page.evaluate(()=>({threads:window.vm.runtime.threads.length,time:Object.values(window.vm.runtime.getTargetForStage().variables).find(v=>v.name==="用时（秒）").value}));
  const stopped=await readStop();
  await page.waitForTimeout(300);
  const stoppedAgain=await readStop();
  if(stopped.threads!==0||stopped.time!==stoppedAgain.time) throw new Error("Stop failed");
  await page.getByTitle("运行", {exact:true}).click();
  pos=xy(-190,-150);
  await page.mouse.move(pos.x,pos.y);
  await page.waitForTimeout(100);
  const restart=await page.evaluate(()=>{
    const t=window.vm.runtime.targets.find(t=>t.getName()==="boat");
    return {x:t.x,y:t.y,costume:t.currentCostume,time:Object.values(window.vm.runtime.getTargetForStage().variables).find(v=>v.name==="用时（秒）").value};
  });
  if(restart.costume!==0||restart.x>-175||restart.time>0.3) throw new Error("Restart failed");
  await page.getByTitle("停止", {exact:true}).click();
  await page.screenshot({path:evidence+"/boat-playing.png"});
  const reopened = await page.evaluate(async () => {
    const blob = await window.vm.saveProjectSb3();
    const bytes = await blob.arrayBuffer();
    await window.vm.loadProject(bytes);
    window.vm.runtime.start();
    const stage = window.vm.runtime.getTargetForStage();
    return {bytes:bytes.byteLength,targets:window.vm.runtime.targets.map(t=>t.getName()),sourceComment:Object.values(stage.comments).some(c=>c.text.includes("Raspberry Pi Foundation")&&c.text.includes("CC BY-SA 4.0"))};
  });
  await page.getByTitle("运行", {exact:true}).click();
  pos=xy(-190,-150);
  await page.mouse.move(pos.x,pos.y);
  await page.waitForTimeout(100);
  const reopenedStarted = await page.evaluate(() => window.vm.runtime.threads.length > 0);
  await page.getByTitle("停止", {exact:true}).click();
  if(!reopened.sourceComment || !reopenedStarted) throw new Error("SB3 export/reopen failed");
  return {sourceProof,test:"actual player / mouse collision / stop / restart / SB3 export and reopen",start,hit,reset,stopped,stoppedAgain,restart,reopened,reopenedStarted};
}
