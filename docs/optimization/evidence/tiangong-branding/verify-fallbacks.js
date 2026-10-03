async page => {
  const checks=[];
  const record=(name,passed,detail)=>{checks.push({name,passed,detail});if(!passed)throw new Error(name+": "+JSON.stringify(detail));};
  const origin="http://127.0.0.1:18133";
  const logoSrc=await page.locator(".campus-masthead img").getAttribute("src");
  const campusSrc=await page.locator(".campus-view img").getAttribute("src");
  const context=await page.context().browser().newContext({viewport:{width:390,height:1000}});
  try {
    const p=await context.newPage();
    await p.route("**/img/wordmark.*.png",r=>r.abort());
    await p.route("**/img/campus.*.jpg",r=>r.abort());
    await p.goto(origin+"/index");
    await p.locator(".campus-image-fallback").waitFor();
    await p.locator(".university-name").waitFor();
    record("campus photo failure retains teaching content",await p.getByRole("heading",{name:"从课堂出发， 让想法成为作品。"}).count()===1&&await p.getByRole("link",{name:"浏览课程"}).isVisible());
    record("wordmark failure retains full school name",(await p.locator(".university-name").innerText()).includes("天津工业大学"));
    await p.screenshot({path:"output/playwright/after-image-failure-390.png",fullPage:true});
    await p.unrouteAll();
    await p.route("**/sys/config/getCurrentConfig*",async route=>{
      const response=await route.fetch();const data=await response.json();
      data.result={...data.result,brandName:"学院课程实验平台",logo:origin+logoSrc,footer:"<p>自定义页脚仍然保留</p>",_homeHtml:"<h1>学院自定义首页</h1><p>已有内容继续显示。</p>"};
      await route.fulfill({response,json:data});
    });
    await p.reload();await p.getByRole("heading",{name:"学院自定义首页",exact:true}).waitFor();
    record("custom home replaces default hero",await p.locator(".welcome-panel").count()===0&&await p.locator(".course-preview").count()===0);
    record("custom platform name and logo retained",await p.getByRole("link",{name:"学院课程实验平台首页",exact:true}).isVisible()&&await p.locator(".brand-logo").evaluate(i=>i.naturalWidth>0));
    record("custom footer and institutional resources coexist",await p.getByText("自定义页脚仍然保留",{exact:true}).isVisible()&&await p.getByRole("navigation",{name:"学校资源",exact:true}).isVisible());
    await p.screenshot({path:"output/playwright/after-custom-config-390.png",fullPage:true});
    await p.unrouteAll();
    await p.route("**/sys/config/getCurrentConfig*",async route=>{
      const response=await route.fetch();const data=await response.json();data.result={...data.result,banner:origin+campusSrc,bannerLinks:"https://www.tiangong.edu.cn/"};await route.fulfill({response,json:data});
    });
    await p.reload();await p.locator(".welcome-banner").waitFor();
    record("configured banner remains preferred",await p.locator(".campus-view").count()===0&&await p.locator(".welcome-banner img").first().evaluate(i=>i.naturalWidth>0));
    const geometry=await p.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));record("configured banner mobile fits",geometry.scroll<=geometry.width,geometry);
    await p.screenshot({path:"output/playwright/after-custom-banner-390.png",fullPage:true});
  } finally {await context.close();}
  return {scope:"Browser-only response interception and asset failure; backend configuration untouched; fresh anonymous context closed",checks};
}
