async (page) => {
  const folder="/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/showcase-five/examples/showcase/scratch/covers";
  await page.setViewportSize({width:960,height:820});
  const captures=[];
  for(const slug of ["boat-race","catch-the-dots"]) {
    await page.goto("http://127.0.0.1:18146/scratch3/player.html?workUrl=/showcase/"+slug+".sb3");
    await page.waitForFunction(()=>window.vm&&window.vm.runtime.targets.some(t=>t.getName()==="玩法与来源"));
    await page.evaluate(()=>{
      const canvas=document.querySelector("canvas");
      canvas.parentElement.parentElement.parentElement.style.transform="none";
      window.vm.renderer.draw();
    });
    const canvas=page.locator("canvas").first();
    await canvas.screenshot({path:folder+"/"+slug+".png"});
    await page.getByTitle("运行",{exact:true}).click();
    if(slug==="boat-race") {
      const rect=await canvas.boundingBox();
      await page.mouse.move(rect.x+50/480*rect.width,rect.y+330/360*rect.height);
      await page.waitForTimeout(100);
    } else {
      await page.waitForTimeout(2400);
    }
    await page.getByTitle("停止",{exact:true}).click();
    await canvas.screenshot({path:folder+"/"+slug+"-playing.png"});
    captures.push({slug,intro:folder+"/"+slug+".png",playing:folder+"/"+slug+"-playing.png",box:await canvas.boundingBox()});
  }
  return captures;
}
