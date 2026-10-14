async (page) => {
  const evidence="/Users/xuzihan/Documents/Projects/TeachingOpen/output/playwright/showcase-five-scratch";
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
  const canvas=page.locator("canvas").first();
  const rect=await canvas.boundingBox();
  const finish={x:210,y:-135};
  await page.getByTitle("运行",{exact:true}).click();
  await page.mouse.move(rect.x+(finish.x+240)/480*rect.width,rect.y+(180-finish.y)/360*rect.height);
  await page.waitForTimeout(100); // Let original green-flag initialization run before fixture setup.
  // This is a targeted real-runtime sensor/finish test, not a full mouse course traversal.
  await page.evaluate(({x,y})=>window.vm.runtime.targets.find(t=>t.getName()==="boat").setXY(x,y),finish);
  await page.waitForTimeout(200);
  await page.screenshot({path:evidence+"/boat-finish-sensor.png"});
  await page.waitForTimeout(1200);
  const ended=await page.evaluate(()=>{
    const boat=window.vm.runtime.targets.find(t=>t.getName()==="boat");
    return {x:boat.x,y:boat.y,threads:window.vm.runtime.threads.length,time:Object.values(window.vm.runtime.getTargetForStage().variables).find(v=>v.name==="用时（秒）").value};
  });
  if(ended.threads!==0||ended.x<190||ended.y>-110) throw new Error("Actual finish sensor did not stop the game");
  await page.getByTitle("运行",{exact:true}).click();
  await page.mouse.move(rect.x+50/480*rect.width,rect.y+330/360*rect.height);
  await page.waitForTimeout(100);
  const restart=await page.evaluate(()=>{
    const boat=window.vm.runtime.targets.find(t=>t.getName()==="boat");
    return {x:boat.x,y:boat.y,threads:window.vm.runtime.threads.length,time:Object.values(window.vm.runtime.getTargetForStage().variables).find(v=>v.name==="用时（秒）").value};
  });
  await page.getByTitle("停止",{exact:true}).click();
  if(restart.threads<1||restart.x>-175||restart.time>0.3) throw new Error("Finish then green-flag restart failed");
  return {sourceProof,test:"actual runtime finish color sensor and green-flag restart",setup:"VM boat.setXY(210,-135) to shorten traversal; collision/reset test uses real mouse only",ended,restart};
}
