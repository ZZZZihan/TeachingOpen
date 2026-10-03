async page => {
  const checks=[];
  const record=(name,passed,detail)=>{checks.push({name,passed,detail});if(!passed)throw new Error(name+": "+JSON.stringify(detail));};
  const geometry=async name=>{const d=await page.evaluate(()=>({path:location.pathname,width:innerWidth,scroll:document.documentElement.scrollWidth}));record(name,d.scroll<=d.width,d);};
  await page.goto("http://127.0.0.1:18133/index");
  await page.getByRole("button",{name:"查看课程：合成测试课程a",exact:true}).waitFor();
  await page.locator("#nprogress").waitFor({state:"hidden"});
  for(const width of [1440,768,390]) {
    await page.setViewportSize({width,height:1000});await geometry("home "+width);
    await page.screenshot({path:"output/playwright/after-home-"+width+".png",fullPage:true});
  }
  const images=await page.evaluate(()=>[...document.querySelectorAll(".campus-masthead img,.campus-view img")].map(i=>({src:i.getAttribute("src"),naturalWidth:i.naturalWidth,complete:i.complete})));
  record("bundled school images decoded",images.length===2&&images.every(i=>i.complete&&i.naturalWidth>0&&!/^https?:/.test(i.src)),images);
  const links=await page.evaluate(()=>[...document.querySelectorAll(".campus-masthead a,.campus-view a,.campus-footer a")].map(a=>({href:a.href,target:a.target,rel:a.rel})));
  record("official links open safely",links.length===4&&links.every(a=>a.href.startsWith("https://")&&a.target==="_blank"&&a.rel.includes("noopener")),links);
  await page.getByRole("button",{name:"展开导航",exact:true}).click();
  record("mobile menu expands",await page.getByRole("button",{name:"收起导航",exact:true}).getAttribute("aria-expanded")==="true");
  await page.getByRole("navigation",{name:"主要导航",exact:true}).getByRole("link",{name:"探索课程",exact:true}).click();
  await page.getByRole("heading",{name:"探索课程",exact:true}).waitFor();
  record("navigation collapses on route",await page.getByRole("button",{name:"展开导航",exact:true}).getAttribute("aria-expanded")==="false");
  await page.getByRole("button",{name:"查看课程：合成测试课程a",exact:true}).waitFor();
  await page.locator("#nprogress").waitFor({state:"hidden"});
  for(const width of [1440,768,390]) {
    await page.setViewportSize({width,height:1000});await geometry("courses "+width);
    await page.screenshot({path:"output/playwright/after-courses-"+width+".png",fullPage:true});
  }
  await page.getByRole("button",{name:"查看课程：合成测试课程a",exact:true}).click();
  await page.getByRole("button",{name:"去上课",exact:true}).waitFor();
  await page.screenshot({path:"output/playwright/after-course-detail-390.png",fullPage:true});
  const buttonColor=await page.getByRole("button",{name:"去上课",exact:true}).evaluate(el=>getComputedStyle(el).backgroundColor);
  record("course dialog uses university primary",buttonColor==="rgb(116, 37, 106)",buttonColor);
  await page.getByRole("button",{name:"去上课",exact:true}).click();
  await page.getByLabel("账号",{exact:true}).waitFor();
  const current=new URL(page.url());record("course entry preserves login destination",current.pathname==="/user/login"&&current.searchParams.get("redirect")==="/teaching/mineCourse/courseUnitCard?id=fixture_course_a",page.url());
  await page.locator("#nprogress").waitFor({state:"hidden"});
  for(const width of [1440,768,390]) {
    await page.setViewportSize({width,height:1000});await geometry("login "+width);
    await page.screenshot({path:"output/playwright/after-login-"+width+".png",fullPage:true});
  }
  const login=await page.evaluate(()=>({inputs:[...document.querySelectorAll("form input")].map(i=>({name:i.name,value:i.value})),captcha:document.querySelector(".captcha-image img")?.naturalWidth}));
  record("login fields empty and captcha image loads",login.inputs.length===3&&login.inputs.every(i=>i.value==="")&&login.captcha>0,login);
  await page.setViewportSize({width:1440,height:1000});await page.goto("http://127.0.0.1:18133/index");
  await page.getByRole("button",{name:"查看课程：合成测试课程a",exact:true}).waitFor();
  return {scope:"Actual built frontend; anonymous synthetic backend; no login or CAPTCHA input",checks};
}
