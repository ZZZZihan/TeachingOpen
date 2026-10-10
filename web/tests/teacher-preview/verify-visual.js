async page => {
  const results = [];
  await page.request.post('http://127.0.0.1:18133/__reset');
  await page.goto('http://127.0.0.1:18134/');
  await page.locator('a:visible').filter({hasText:/^批改$/}).first().waitFor();
  for (const width of [1440,768,390]) {
    await page.setViewportSize({width,height:1000});
    await page.screenshot({path:`output/playwright/teacher-before-list-${width}.png`,fullPage:true});
    results.push({page:'before-list',width,scrollWidth:await page.evaluate(()=>document.documentElement.scrollWidth)});
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('a:visible').filter({hasText:/^批改$/}).first().click();
  await page.getByRole('dialog').waitFor();
  await page.screenshot({path:'output/playwright/teacher-before-grading-1440.png',fullPage:true});
  await page.goto('http://127.0.0.1:18133/');
  await page.getByRole('button',{name:'开始批改'}).first().waitFor();
  for (const width of [1440,768,390]) {
    await page.setViewportSize({width,height:1000});
    await page.screenshot({path:`output/playwright/teacher-after-list-${width}.png`,fullPage:true});
    const scrollWidth=await page.evaluate(()=>document.documentElement.scrollWidth);
    if(scrollWidth>width) throw new Error(`List overflow at ${width}: ${scrollWidth}`);
    results.push({page:'after-list',width,scrollWidth,rows:await page.locator('.work-row').count()});
    await page.getByRole('button',{name:'开始批改'}).first().click();
    await page.getByRole('textbox',{name:'评语',exact:true}).waitFor();
    await page.getByRole('radio',{name:'0',exact:true}).check();
    await page.getByRole('textbox',{name:'评语',exact:true}).fill('请补充实验过程的记录，尤其是你观察到的变化。');
    await page.screenshot({path:`output/playwright/teacher-after-grading-${width}.png`,fullPage:false});
    if(width===390) {await page.getByRole('button',{name:'保存批改',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:'output/playwright/teacher-after-grading-390-footer.png'});}
    const box=await page.locator('.ant-modal-content').last().boundingBox();
    if(box.x<0 || box.x+box.width>width+1) throw new Error(`Dialog overflow at ${width}`);
    results.push({page:'after-grading',width,dialogWidth:box.width,zeroSelected:await page.getByRole('radio',{name:'0',exact:true}).isChecked()});
    await page.goto('http://127.0.0.1:18133/');
    await page.getByRole('button',{name:'开始批改'}).first().waitFor();
  }
  return results;
}