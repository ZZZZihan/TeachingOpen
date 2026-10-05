(() => {
  'use strict';
  const storageKey = 'teachingopen-club-preview-v1';
  const defaults = { sides: 4, repeats: 12, rotation: 28, color: '#146d5d' };
  const palette = [
    { value: '#146d5d', name: '松绿' },
    { value: '#3d6391', name: '湖蓝' },
    { value: '#b84c31', name: '陶红' },
  ];
  const steps = [
    { title: '先试一试', text: '拖动「旋转角度」，观察图案哪里变了。先随意试几次，再选一个你喜欢的角度。没有标准答案，先让好奇心带路。', action: '我试过了，继续观察' },
    { title: '发现规律', text: '固定多边形和重复次数，只改变旋转角度。试试 15°、30° 和 45°：哪些图案看起来更整齐？哪些线条重叠在了一起？', action: '我找到了一点规律' },
    { title: '做我的作品', text: '选一种颜色，改变多边形边数和重复次数，画出一个属于你的图案。你可以参考下面的基础任务，也可以直接尝试自己的组合。', action: '我的图案准备好了' },
    { title: '说说想法', text: '给作品起个名字。在旁边的「我的发现」里写下你改变了什么、为什么这样选。然后保存到本机，再到创作台看看自己的作品。', action: '我能解释自己的选择' },
  ];
  const state = { params: { ...defaults }, title: '我的几何花园', note: '', completed: [], tasks: [], step: 0, tab: 'steps', interest: 'all', savedAt: null, dirty: false, suggestionVisible: false };
  let savedWork = null;
  let storageAvailable = true;
  let oldRecordUnreadable = false;
  let initialRender = true;
  const main = document.querySelector('#main');
  const announcer = document.querySelector('#announcer');
  const dialog = document.querySelector('#project-dialog');

  const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const clamp = (value, min, max, fallback) => Number.isFinite(Number(value)) ? Math.min(max, Math.max(min, Math.round(Number(value)))) : fallback;
  function safeParams(input = {}) {
    return {
      sides: clamp(input.sides, 3, 8, defaults.sides),
      repeats: clamp(input.repeats, 4, 24, defaults.repeats),
      rotation: clamp(input.rotation, 5, 90, defaults.rotation),
      color: palette.some((color) => color.value === input.color) ? input.color : defaults.color,
    };
  }
  let storedRecord = null;
  try { storedRecord = localStorage.getItem(storageKey); }
  catch (_) { storageAvailable = false; }
  try {
    const candidate = storedRecord === null ? null : JSON.parse(storedRecord);
    if (candidate && candidate.version === 1 && candidate.params && typeof candidate.params === 'object' && typeof candidate.title === 'string' && typeof candidate.note === 'string' && typeof candidate.savedAt === 'string' && !Number.isNaN(Date.parse(candidate.savedAt))) {
      savedWork = { ...candidate, title: candidate.title.slice(0, 30), note: candidate.note.slice(0, 500), params: safeParams(candidate.params), completed: Array.isArray(candidate.completed) ? candidate.completed.filter((n) => Number.isInteger(n) && n >= 0 && n < 4) : [], tasks: Array.isArray(candidate.tasks) ? candidate.tasks.filter((n) => Number.isInteger(n) && n >= 0 && n < 3) : [] };
      Object.assign(state, { params: { ...savedWork.params }, title: savedWork.title, note: savedWork.note, completed: [...new Set(savedWork.completed)], tasks: [...new Set(savedWork.tasks)], savedAt: savedWork.savedAt });
      state.step = Math.min(state.completed.length, 3);
    } else if (storedRecord !== null) { oldRecordUnreadable = true; }
  } catch (_) { oldRecordUnreadable = true; }

  function geometrySVG(params, label = '重复旋转的多边形组成的几何图案', options = {}) {
    const width = options.width || 680;
    const height = options.height || 430;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * .34;
    const pointString = Array.from({ length: params.sides }, (_, i) => {
      const radians = (i * 360 / params.sides - 90) * Math.PI / 180;
      return `${(radius * Math.cos(radians)).toFixed(2)},${(radius * Math.sin(radians)).toFixed(2)}`;
    }).join(' ');
    const polygons = Array.from({ length: params.repeats }, (_, i) => `<polygon points="${pointString}" transform="rotate(${i * params.rotation})"/>`).join('');
    const grid = options.grid ? `<g stroke="#d8e0d2" stroke-width=".7">${Array.from({ length: 18 }, (_, i) => `<path d="M${i * 40} 0V${height}"/>`).join('')}${Array.from({ length: 12 }, (_, i) => `<path d="M0 ${i * 40}H${width}"/>`).join('')}</g>` : '';
    const annotations = options.annotations ? `<g fill="#526259" font-family="system-ui,sans-serif" font-size="10"><text x="26" y="30">EXPERIMENT / 01</text><text x="26" y="${height - 22}">${params.sides} 边形 × ${params.repeats} 次旋转</text><text x="${width - 27}" y="${height - 22}" text-anchor="end">${params.rotation}°</text></g><g stroke="#526259" stroke-width=".7"><path d="M${centerX - radius - 26} ${centerY}h13m-6.5-6.5v13M${centerX + radius + 13} ${centerY}h13m-6.5-6.5v13"/></g>` : '';
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(label)}" xmlns="http://www.w3.org/2000/svg">${grid}<circle cx="${centerX}" cy="${centerY}" r="${radius + 20}" stroke="#c9d3c3" stroke-width=".8" stroke-dasharray="2 6" fill="none"/><g transform="translate(${centerX} ${centerY})" fill="none" stroke="${params.color}" stroke-width="1.35" opacity=".84">${polygons}</g><circle cx="${centerX}" cy="${centerY}" r="2.5" fill="${params.color}"/>${annotations}</svg>`;
  }

  function soundSVG() {
    const bars = Array.from({ length: 33 }, (_, i) => {
      const waveHeight = 10 + Math.abs(Math.sin(i * 1.43) * Math.cos(i * .36)) * 70;
      return `<path d="M${27 + i * 7.7} ${126 - waveHeight / 2}v${waveHeight}"/>`;
    }).join('');
    return `<svg viewBox="0 0 310 260" role="img" aria-label="原创声音项目预览：波形与收音线条" xmlns="http://www.w3.org/2000/svg"><rect width="310" height="260" fill="#e8decb"/><g fill="none" stroke="#b84c31"><circle cx="245" cy="60" r="21" stroke-width="1.4"/><circle cx="245" cy="60" r="30" stroke-width=".7" stroke-dasharray="2 3"/><path d="M234 60h22m-11-11v22" stroke-width="1.2"/><g stroke-width="2.7" stroke-linecap="round">${bars}</g></g><path d="M24 187h260M24 198h153M24 209h194" stroke="#c3b399" stroke-width="1"/><g fill="#895f48" font-family="system-ui,sans-serif" font-size="9"><text x="24" y="34">SOUND NOTES</text><text x="24" y="239">听见身边的声音</text></g></svg>`;
  }

  function bridgeSVG() {
    return `<svg viewBox="0 0 310 260" role="img" aria-label="原创结构项目预览：三角形桥梁设计图" xmlns="http://www.w3.org/2000/svg"><rect width="310" height="260" fill="#dee5e9"/><g stroke="#c8d1d6" stroke-width=".65">${Array.from({length: 10}, (_, i) => `<path d="M${i * 34} 0v260M0 ${i * 30}h310"/>`).join('')}</g><g fill="none" stroke="#3d6391" stroke-linejoin="round"><path d="M29 170L70 105l42 65 42-65 42 65 42-65 43 65zM29 170h252M70 105h168" stroke-width="2.2"/><path d="M70 105v65m42-65v65m42-65v65m42-65v65m42-65v65" stroke-width="1"/><path d="M22 195h267M29 188v14m252-14v14" stroke-width=".8"/></g><g fill="#3d6391">${[29,70,112,154,196,238,281].map((x, i) => `<circle cx="${x}" cy="${i % 2 ? 105 : 170}" r="3.5"/>`).join('')}<path d="M147 60h14v18h8l-15 17-15-17h8z"/></g><g fill="#526a7b" font-family="system-ui,sans-serif" font-size="9"><text x="24" y="34">STRUCTURE STUDY</text><text x="115" y="218">让三角形来帮忙</text></g></svg>`;
  }

  function projectTiles() {
    const geometry = `<article class="featured-project"><div class="project-identity"><div><span class="eyebrow">艺术 × 数学 · 可操作演示</span><h2>让几何动起来</h2><p>改变一个角度，让简单线条长成你的图案。</p></div><a class="button button-primary project-enter" href="#/learn/geometry">进入几何画室 <span aria-hidden="true">↗</span></a></div><div class="project-art">${geometrySVG({ sides: 4, repeats: 18, rotation: 17, color: '#146d5d' }, '原创项目预览：细线组成的旋转几何花园', { width: 620, height: 500, grid: true, annotations: true })}</div></article>`;
    const sound = `<article class="project-small"><div class="project-art">${soundSVG()}</div><div><span class="eyebrow">声音 × 表达 · 概念演示</span><h3>给校园留个声音</h3><p>从一段熟悉的声音，开始观察日常。</p><button type="button" class="text-link" data-action="project-idea" data-project="sound">看看项目想法 <span aria-hidden="true">↗</span></button></div></article>`;
    const bridge = `<article class="project-small"><div class="project-art">${bridgeSVG()}</div><div><span class="eyebrow">设计 × 工程 · 概念演示</span><h3>一张纸的桥梁</h3><p>试着让轻巧的纸，撑住更多可能。</p><button type="button" class="text-link" data-action="project-idea" data-project="bridge">看看项目想法 <span aria-hidden="true">↗</span></button></div></article>`;
    if (state.interest === 'art') return geometry;
    if (state.interest === 'sound') return sound;
    if (state.interest === 'design') return bridge;
    return geometry + sound + bridge;
  }

  function homePage() {
    return `<div class="shell"><section class="home-intro" aria-labelledby="home-title"><div><span class="eyebrow">给好奇心一点动手的空间</span><h1 id="home-title"><span>从一个小想法，</span><span>到一件自己的作品。</span></h1></div><div class="intro-copy"><p>画一个图案，听一种声音，试一种结构。<br>在社团和课后，和自己的好奇心碰个面。</p><a class="text-link" href="#/studio">已有灵感？去创作台接着做 <span aria-hidden="true">↗</span></a></div></section><section aria-label="按兴趣探索演示项目"><div class="interest-row"><span class="interest-label">今天想试什么？</span>${[['all','随便逛逛'],['art','艺术与数学'],['sound','声音与表达'],['design','设计与工程']].map(([key,label])=>`<button type="button" class="interest" data-action="filter" data-interest="${key}" aria-pressed="${state.interest === key}">${label}</button>`).join('')}</div><div id="project-grid" class="project-grid">${projectTiles()}</div></section><section class="home-process" aria-labelledby="process-title"><div><span class="eyebrow">不必先知道所有答案</span><h2 id="process-title">边做，边找到自己的办法。</h2></div><div class="process-line"><div><span>01</span><h3>挑一个感兴趣的</h3><p>从身边的问题或喜欢的作品出发。</p></div><div><span>02</span><h3>先动手试一试</h3><p>改一点，观察一点，留下一点发现。</p></div><div><span>03</span><h3>做成自己的样子</h3><p>给作品起个名字，也说说你的选择。</p></div></div></section></div>`;
  }

  function stepPanel() {
    const detail = steps[state.step];
    return `<div class="step-nav" aria-label="选择学习步骤">${steps.map((step, i) => `<button type="button" class="${state.completed.includes(i) ? 'is-done' : ''}" data-action="step" data-step="${i}" aria-pressed="${state.step === i}"><span>0${i + 1}</span>${step.title}</button>`).join('')}</div><div class="step-detail"><h2>${detail.title}</h2><p>${detail.text}</p><button type="button" class="button button-quiet" data-action="complete-step">${state.completed.includes(state.step) ? '已完成这一步 · 再看下一步' : detail.action}<span aria-hidden="true">→</span></button></div>`;
  }
  function basicPanel() {
    const tasks = ['试过至少两种旋转角度，并观察图案的变化。', '调整多边形边数，找到一个自己喜欢的组合。', '给作品起名，在「我的发现」里解释一个选择。'];
    return `<div class="task-detail"><h2>做一个你能解释的图案</h2><p>这里没有唯一答案。做完一项，就给自己打个勾。</p><ul class="task-list">${tasks.map((task, i) => `<li><label><input type="checkbox" data-task="${i}" ${state.tasks.includes(i) ? 'checked' : ''}><span>${task}</span></label></li>`).join('')}</ul><div class="task-result" id="task-result">已自评完成 ${state.tasks.length} / 3 项。这是自己的练习记录。</div></div>`;
  }
  function challengePanel() {
    return `<div class="task-detail"><h2>让图案藏一个规律</h2><p>只改变一个参数，做出两幅风格不同的图案。猜猜：旋转角度正好能整除 360° 时，会发生什么？用自己的话说说为什么。</p><div class="challenge-example">${geometrySVG({sides: 3, repeats: 18, rotation: 20, color: '#b84c31'}, '挑战示例：三角形重复旋转形成的花纹', {width: 150, height: 150})}<div><p>先试试 3 边形、18 次、20°。<br>这是一个起点，接下来由你改。</p><button type="button" class="text-link" data-action="challenge-preset">在画布里试这个组合 <span aria-hidden="true">↗</span></button></div></div></div>`;
  }
  function getSuggestion() {
    if (!state.note.trim()) return '你的图案已经有自己的样子了。下一步，试着记下「我改了什么」和「我观察到什么」，这样下次就能接着探索。';
    if (state.params.repeats > 16) return '线条重复得比较多，图案很丰富。试着保持其他参数不变，把重复次数减半，比较一下：哪一种更容易看清规律？';
    return '你已经留下了自己的发现。可以再试一次：只改旋转角度，把两次结果放在心里比较，看看你的猜测是否成立。';
  }
  function feedbackPanel() {
    return `<div class="feedback-detail"><h2>给下一步找个小线索</h2><p>这里会根据当前图案和练习笔记，给出一条固定规则生成的演示建议。你可以采纳，也可以沿着自己的想法继续。</p><button type="button" class="button button-quiet" data-action="suggestion">${state.suggestionVisible ? '再看看当前建议' : '看一条演示建议'} <span aria-hidden="true">↗</span></button>${state.suggestionVisible ? `<div class="suggestion" role="status"><span class="eyebrow">规则建议演示 · 非老师反馈</span><p>${getSuggestion()}</p></div>` : ''}</div>`;
  }
  function activePanel() {
    return ({ steps: stepPanel, basic: basicPanel, challenge: challengePanel, feedback: feedbackPanel })[state.tab]();
  }
  function saveLabel() { return state.savedAt && !state.dirty ? '已保存到本机 ✓' : '保存到本机'; }
  function saveCaption() {
    if (!storageAvailable) return '当前浏览器无法保存。你仍可在本页练习，刷新后会丢失当前内容。';
    if (oldRecordUnreadable) return '旧记录未能读取。你仍可将当前练习保存到本机。';
    return state.savedAt && !state.dirty ? `保存在当前浏览器 · ${formatDate(state.savedAt)}。没有发送给老师。` : '只保存在当前浏览器。保存后，可从创作台继续。';
  }
  function learnPage() {
    return `<div class="shell"><section class="page-top"><div class="breadcrumb"><a href="#/">探索项目</a><span aria-hidden="true">/</span><span>几何画室</span></div><div class="learning-title"><div><h1>让几何动起来</h1><p>改一个参数，观察一次变化。把规律画成自己的作品。</p></div><div class="project-meta">艺术 × 数学 · 原创演示</div></div></section><section class="workbench" aria-label="几何画室交互演示"><div class="canvas-area"><div class="canvas-topline"><strong>你的实验画布</strong><span>实时演示 · 无需安装</span></div><div class="drawing-canvas" id="drawing-canvas">${geometrySVG(state.params, '当前几何画布，可使用旁边的参数实时改变图案', {grid: true, annotations: true})}</div><div class="canvas-description"><span id="pattern-summary">${state.params.sides} 边形 · 重复 ${state.params.repeats} 次 · 每次旋转 ${state.params.rotation}°</span><span>一次只改一项，看看有什么不同。</span></div></div><div class="controls"><h2>试着改一点</h2><p>拖动滑块，图案会立刻跟着变化。</p>${[['sides','多边形边数',3,8,'边','从三角形，到八边形。'],['repeats','重复次数',4,24,'次','更多线条，也会带来更多重叠。'],['rotation','旋转角度',5,90,'°','每画一次，转过这么多角度。']].map(([key,label,min,max,unit,help])=>`<div class="control"><label class="control-label" for="${key}"><span>${label}</span><output for="${key}" id="${key}-value">${state.params[key]}${unit}</output></label><input id="${key}" type="range" min="${min}" max="${max}" value="${state.params[key]}" data-param="${key}" aria-describedby="${key}-help"><p class="control-help" id="${key}-help">${help}</p></div>`).join('')}<div class="control"><span class="control-label" id="color-label">线条颜色</span><div class="color-options" role="group" aria-labelledby="color-label">${palette.map((color) => `<button type="button" class="color-choice" style="--swatch:${color.value}" data-action="color" data-color="${color.value}" aria-label="${color.name}" aria-pressed="${state.params.color === color.value}"></button>`).join('')}</div></div><div class="control-actions"><button type="button" class="button button-primary" data-action="save" id="save-button">${saveLabel()}</button><button type="button" class="button button-quiet" data-action="reset">恢复初始图案</button></div><p class="save-caption" id="save-caption">${saveCaption()}</p></div></section><section class="learning-lower" aria-label="学习任务与创作记录"><div><div class="learning-tabs" role="tablist" aria-label="项目学习内容">${[['steps','学习步骤'],['basic','基础任务'],['challenge','进阶挑战'],['feedback','看看建议']].map(([key,label])=>`<button type="button" role="tab" id="tab-${key}" data-action="tab" data-tab="${key}" aria-selected="${state.tab === key}" aria-controls="learning-panel" tabindex="${state.tab === key ? 0 : -1}">${label}</button>`).join('')}</div><div class="tab-panel" id="learning-panel" role="tabpanel" aria-labelledby="tab-${state.tab}" tabindex="0">${activePanel()}</div></div><aside class="learning-notes" aria-labelledby="notes-title"><h2 id="notes-title">留下你的发现</h2><p>作品不只是图案，还可以是你发现的一点小规律。</p><label for="work-title">作品名字</label><input type="text" class="text-input" id="work-title" maxlength="30" value="${escapeHTML(state.title)}" placeholder="给它起个名字"><label for="work-note">我的发现</label><textarea id="work-note" maxlength="500" placeholder="我把角度从……改成……，发现……">${escapeHTML(state.note)}</textarea><p class="save-caption">名字和笔记会和图案一起保存到本机。<br>保存后到 <a class="text-link" href="#/studio">创作台</a> 看看自己的作品。</p></aside></section></div>`;
  }
  function formatDate(value) {
    return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
  }
  function studioPage() {
    const hasSaved = !!savedWork;
    const hasDraft = state.dirty || hasSaved;
    const title = hasDraft ? (state.title.trim() || '未命名的几何作品') : '我的几何花园';
    const progress = state.completed.length;
    return `<div class="shell"><section class="page-top studio-title"><div><span class="eyebrow">我的创作台 · 当前浏览器</span><h1>${hasSaved ? '接着把想法做出来。' : '第一件作品，从这里开始。'}</h1><p>${hasSaved ? '你留下的图案和发现，等你继续。' : '先试一试，再把喜欢的图案留下来。'}</p></div><div class="local-status"><span class="status-dot" aria-hidden="true"></span>${hasSaved ? (state.dirty ? '有尚未保存的修改' : `本机保存于 ${formatDate(state.savedAt)}`) : '示例创作台 · 尚未保存作品'}</div></section><section class="studio-main" aria-labelledby="studio-work-title"><div class="studio-preview">${geometrySVG(state.params, '当前几何作品预览', {width: 680, height: 430, grid: true, annotations: true})}<div class="studio-preview-caption"><span>${hasDraft ? '当前练习预览' : '原创示例图案'} · 几何画室</span><span>${palette.find((color)=>color.value===state.params.color).name} / ${state.params.rotation}°</span></div></div><div class="studio-work"><span class="eyebrow">${hasSaved ? '本机作品' : '演示草稿'} · 艺术 × 数学</span><h2 id="studio-work-title">${escapeHTML(title)}</h2><p>${hasSaved ? '再试一种组合，或者回到上次的发现。一次小小的变化，也可能带来新的灵感。' : '用重复和旋转，画一幅自己的几何图案。这里展示的是示例，动手后可以保存成你的本机作品。'}</p><div class="work-progress"><div class="work-progress-info"><span>我的步骤记录 · 本机</span><span>${progress} / 4</span></div><div class="progress-track" role="progressbar" aria-label="自己标记的步骤记录" aria-valuemin="0" aria-valuemax="4" aria-valuenow="${progress}"><span style="width:${progress * 25}%"></span></div></div><div class="studio-actions"><a class="button button-primary" href="#/learn/geometry">${hasDraft ? '继续我的作品' : '试试几何画室'} <span aria-hidden="true">↗</span></a><a class="text-link" href="#/learn/geometry/feedback">读一条演示建议 <span aria-hidden="true">→</span></a></div></div></section><section class="studio-below" aria-label="我的发现与下一步"><div><span class="eyebrow">回头看一眼，会有新发现</span><h2>我的创作笔记</h2><p>${state.note.trim() ? '你为这次练习留下了这些想法：' : '还没有留下笔记。试着记下改过的参数，或者图案带给你的联想。'}</p>${state.note.trim() ? `<p class="studio-note">${escapeHTML(state.note)}</p>` : ''}<a class="text-link" href="#/learn/geometry/notes">回到作品，记下我的发现 <span aria-hidden="true">↗</span></a></div><div class="studio-suggestion"><span class="eyebrow">下一步灵感 · 固定规则建议演示</span><h2>只改一项，再试一次。</h2><p>${getSuggestion()}</p><a class="text-link" href="#/learn/geometry/challenge">试试进阶挑战 <span aria-hidden="true">↗</span></a></div></section><p class="studio-disclosure">这是设计原型中的本机创作台。没有账号或在线作业记录；当前作品、步骤自评与笔记只会在点击「保存到本机」后留在当前浏览器。</p></div>`;
  }

  function announce(message) {
    announcer.textContent = '';
    window.setTimeout(() => { announcer.textContent = message; }, 40);
  }
  function markDirty() {
    state.dirty = true;
    const button = document.querySelector('#save-button');
    if (button) button.textContent = saveLabel();
    const caption = document.querySelector('#save-caption');
    if (caption) caption.textContent = saveCaption();
  }
  function updateCanvas() {
    const canvas = document.querySelector('#drawing-canvas');
    if (canvas) canvas.innerHTML = geometrySVG(state.params, '当前几何画布，可使用旁边的参数实时改变图案', {grid: true, annotations: true});
    const summary = document.querySelector('#pattern-summary');
    if (summary) summary.textContent = `${state.params.sides} 边形 · 重复 ${state.params.repeats} 次 · 每次旋转 ${state.params.rotation}°`;
    for (const [key, unit] of [['sides', '边'], ['repeats', '次'], ['rotation', '°']]) {
      const output = document.querySelector(`#${key}-value`);
      const range = document.querySelector(`#${key}`);
      if (output) output.textContent = `${state.params[key]}${unit}`;
      if (range) range.value = state.params[key];
    }
    document.querySelectorAll('[data-action="color"]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.color === state.params.color)));
  }
  function selectTab(tab, moveFocus = false) {
    if (!['steps', 'basic', 'challenge', 'feedback'].includes(tab)) return;
    state.tab = tab;
    document.querySelectorAll('[role="tab"]').forEach((button) => {
      const selected = button.dataset.tab === tab;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
      if (selected && moveFocus) button.focus();
    });
    const panel = document.querySelector('#learning-panel');
    if (panel) {
      panel.innerHTML = activePanel();
      panel.setAttribute('aria-labelledby', `tab-${tab}`);
    }
  }
  function renderRoute() {
    const hash = location.hash || '#/';
    const learn = hash.startsWith('#/learn/geometry');
    const studio = hash === '#/studio';
    if (learn) {
      const subRoute = hash.split('/')[3];
      if (subRoute === 'feedback' || subRoute === 'challenge') state.tab = subRoute;
      if (subRoute === 'feedback') state.suggestionVisible = true;
      main.innerHTML = learnPage();
      document.title = '几何画室 · 开放创作';
    } else if (studio) {
      main.innerHTML = studioPage();
      document.title = '我的创作台 · 开放创作';
    } else {
      main.innerHTML = homePage();
      document.title = '探索项目 · 开放创作';
    }
    document.querySelectorAll('[data-route]').forEach((link) => {
      const current = (link.dataset.route === 'studio' && studio) || (link.dataset.route === 'home' && !studio && !learn);
      if (current) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    if (dialog.open) dialog.close();
    window.scrollTo(0, 0);
    if (!initialRender) main.focus({ preventScroll: true });
    initialRender = false;
    if (learn && hash.endsWith('/notes')) {
      const titleInput = document.querySelector('#work-title');
      titleInput.scrollIntoView({block: 'center'});
      titleInput.focus({preventScroll: true});
    }
  }
  function saveWork() {
    const work = { version: 1, params: { ...state.params }, title: state.title.trim() || '未命名的几何作品', note: state.note, completed: [...state.completed], tasks: [...state.tasks], savedAt: new Date().toISOString() };
    try {
      localStorage.setItem(storageKey, JSON.stringify(work));
      savedWork = work;
      state.title = work.title;
      state.savedAt = work.savedAt;
      state.dirty = false;
      storageAvailable = true;
      oldRecordUnreadable = false;
      document.querySelector('#save-button').textContent = saveLabel();
      document.querySelector('#save-caption').textContent = saveCaption();
      document.querySelector('#work-title').value = state.title;
      announce('图案、名字和练习记录已保存到当前浏览器。可以去创作台继续。');
    } catch (_) {
      storageAvailable = false;
      document.querySelector('#save-caption').textContent = saveCaption();
      announce('当前浏览器无法保存，内容仍留在这次页面中。');
    }
  }
  function showProjectIdea(project) {
    const content = project === 'sound'
      ? `${soundSVG()}<h2 id="dialog-title">给校园留个声音</h2><p>找一段你熟悉的声音：课间脚步、风吹树叶、操场上的哨声。想一想，如果只用声音介绍一个地方，你会怎样组织它们？</p>`
      : `${bridgeSVG()}<h2 id="dialog-title">一张纸的桥梁</h2><p>同一张纸，平放、折叠和卷起，承重会一样吗？这个项目想从简单材料出发，用反复尝试找到轻巧又稳定的结构。</p>`;
    document.querySelector('#dialog-content').innerHTML = `<div class="dialog-art">${content.slice(0, content.indexOf('<h2'))}</div>${content.slice(content.indexOf('<h2'))}`;
    dialog.showModal();
  }
  document.addEventListener('click', (event) => {
    if (event.target.closest('.skip-link')) {
      event.preventDefault();
      main.scrollIntoView({ block: 'start' });
      main.focus({ preventScroll: true });
      return;
    }
    const button = event.target.closest('[data-action]');
    if (!button) return;
    switch (button.dataset.action) {
      case 'filter':
        state.interest = button.dataset.interest;
        document.querySelectorAll('[data-action="filter"]').forEach((item) => item.setAttribute('aria-pressed', String(item.dataset.interest === state.interest)));
        document.querySelector('#project-grid').innerHTML = projectTiles();
        announce(`已显示${button.textContent}的演示项目。`);
        break;
      case 'project-idea': showProjectIdea(button.dataset.project); break;
      case 'close-dialog': dialog.close(); break;
      case 'color':
        state.params.color = button.dataset.color;
        markDirty(); updateCanvas();
        announce(`线条颜色已改为${palette.find((color) => color.value === state.params.color).name}。`);
        break;
      case 'reset':
        state.params = { ...defaults };
        markDirty(); updateCanvas();
        announce('已恢复初始图案。名字、笔记和学习记录保留。');
        break;
      case 'save': saveWork(); break;
      case 'tab': selectTab(button.dataset.tab); break;
      case 'step':
        state.step = Number(button.dataset.step);
        selectTab('steps');
        document.querySelector(`[data-action="step"][data-step="${state.step}"]`).focus();
        break;
      case 'complete-step':
        if (!state.completed.includes(state.step)) state.completed.push(state.step);
        markDirty();
        const completedStep = state.step;
        state.step = Math.min(state.step + 1, 3);
        selectTab('steps');
        document.querySelector(`[data-action="step"][data-step="${state.step}"]`).focus();
        announce(`已将第 ${completedStep + 1} 步标记为完成。点击保存到本机可保留进度。`);
        break;
      case 'challenge-preset':
        state.params = { sides: 3, repeats: 18, rotation: 20, color: '#b84c31' };
        markDirty(); updateCanvas();
        document.querySelector('#drawing-canvas').scrollIntoView({ block: 'center' });
        document.querySelector('#rotation').focus({ preventScroll: true });
        announce('已换成挑战示例：3 边形，重复 18 次，每次旋转 20 度。');
        break;
      case 'suggestion':
        state.suggestionVisible = true;
        selectTab('feedback');
        document.querySelector('[data-action="suggestion"]').focus();
        break;
      default: break;
    }
  });
  document.addEventListener('input', (event) => {
    const target = event.target;
    if (target.dataset.param) {
      state.params[target.dataset.param] = Number(target.value);
      markDirty(); updateCanvas();
    } else if (target.id === 'work-title') {
      state.title = target.value; markDirty();
    } else if (target.id === 'work-note') {
      state.note = target.value; markDirty();
    }
  });
  document.addEventListener('change', (event) => {
    const target = event.target;
    if (target.dataset.task !== undefined) {
      const task = Number(target.dataset.task);
      if (target.checked && !state.tasks.includes(task)) state.tasks.push(task);
      if (!target.checked) state.tasks = state.tasks.filter((item) => item !== task);
      markDirty();
      document.querySelector('#task-result').textContent = `已自评完成 ${state.tasks.length} / 3 项。这是自己的练习记录。`;
    }
    if (target.dataset.param) announce(`图案已更新：${state.params.sides} 边形，重复 ${state.params.repeats} 次，每次旋转 ${state.params.rotation} 度。`);
  });
  document.addEventListener('keydown', (event) => {
    if (event.target.getAttribute('role') !== 'tab') return;
    const keys = ['steps', 'basic', 'challenge', 'feedback'];
    const index = keys.indexOf(state.tab);
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % keys.length;
    else if (event.key === 'ArrowLeft') next = (index + keys.length - 1) % keys.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = keys.length - 1;
    else return;
    event.preventDefault();
    selectTab(keys[next], true);
  });
  window.addEventListener('hashchange', renderRoute);
  renderRoute();
})();
