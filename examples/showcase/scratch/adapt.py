"""Rebuild the two attributed showcase files from fixed upstream SB3 archives."""
from pathlib import Path
import copy
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
ITEMS = [
    dict(slug="boat-race", title="小船竞速", original_title="Boat race", commit="08b40cde7e8bd804bd1b0f7bed335123115f8f24", upstream_path="en/solutions/BoatRace-Finished.sb3", project="https://scratch.mit.edu/projects/276662533/", instructions="移动鼠标，带领小船穿过水道。", goal="避开棕色河岸，驶向右下角的浅黄色终点。", detail="碰到河岸会回到起点；白色水流会让小船加速。"),
    dict(slug="catch-the-dots", title="缤纷接点", original_title="Catch the Dots", commit="beeafc3a77a993c762c4017ad66cd3385d6deac3", upstream_path="en/solutions/catch-the-dots-solution.sb3", project="https://scratch.mit.edu/projects/252923761/", instructions="按左右方向键，旋转中央的三色转盘。", goal="用相同颜色接住飞来的圆点，每接对一次加 1 分。", detail="接错会失去一次机会；3 次机会用完，游戏结束。"),
]


def block(opcode, *, parent=None, next=None, inputs=None, fields=None, top=False):
    value = dict(opcode=opcode, next=next, parent=parent, inputs=inputs or {}, fields=fields or {}, topLevel=top, shadow=False)
    if top:
        value.update(x=40, y=40)
    return value


def sprite(name, costume, *, visible, layer, x=0, y=0):
    return dict(isStage=False, name=name, variables={}, lists={}, broadcasts={}, blocks={}, comments={}, currentCostume=0, costumes=[costume], sounds=[], volume=100, layerOrder=layer, visible=visible, x=x, y=y, size=100, direction=90, draggable=False, rotationStyle="don't rotate")


def costume(assets, name, svg, width, height):
    data = svg.encode("utf-8")
    md5 = hashlib.md5(data).hexdigest()
    assets[md5 + ".svg"] = data
    return dict(assetId=md5, name=name, bitmapResolution=1, md5ext=md5 + ".svg", dataFormat="svg", rotationCenterX=width/2, rotationCenterY=height/2)


def intro_svg(item):
    boat = item["slug"] == "boat-race"
    accent = "#39c9b0" if boat else "#ffba54"
    icon = '<path d="M55 15L78 46H29Z" fill="#a7f0e6"/><path d="M18 49H85L72 66H33Z" fill="#39c9b0"/><path d="M48 10V47" stroke="#e3edf8" stroke-width="3"/>' if boat else '<circle cx="40" cy="35" r="23" fill="#fa686f"/><circle cx="68" cy="55" r="23" fill="#f7bf49"/><circle cx="20" cy="63" r="23" fill="#5d9cfa"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360">
<rect width="480" height="360" fill="#11253c"/>
<circle cx="440" cy="15" r="140" fill="#193550"/><circle cx="10" cy="360" r="120" fill="#17334b"/>
<g transform="translate(35,23)">{icon}</g>
<g font-family="PingFang SC, Microsoft YaHei, sans-serif" fill="#e3edf8">
<text x="135" y="60" font-size="30" font-weight="700">{item['title']}</text>
<text x="136" y="86" font-size="12" fill="#a8bdce">{item['original_title']} · 互动编程精选</text>
<rect x="35" y="120" width="410" height="142" rx="16" fill="#1b3853"/>
<text x="55" y="153" font-size="15" font-weight="600">{item['instructions']}</text>
<text x="55" y="185" font-size="13">{item['goal']}</text>
<text x="55" y="214" font-size="12" fill="#b7cada">{item['detail']}</text>
<text x="55" y="243" font-size="12" fill="#b7cada">点红色按钮停止游戏，再点绿旗重新开始。</text>
<rect x="135" y="276" width="210" height="35" rx="17" fill="{accent}"/>
<text x="240" y="300" text-anchor="middle" font-size="14" font-weight="700" fill="#11253c">点击上方绿旗开始游戏</text>
<text x="240" y="337" text-anchor="middle" font-size="10" fill="#a8bdce">原作 Raspberry Pi Foundation · CC BY-SA 4.0 · TeachingOpen 中文适配</text>
</g></svg>'''


def footer_svg():
    # Avoid every gameplay collision color used by either upstream project.
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="255" height="15" viewBox="0 0 255 15"><rect width="255" height="15" rx="4" fill="#152c43"/><text x="127.5" y="10.5" text-anchor="middle" font-family="Arial, sans-serif" font-size="8" fill="#dce8f4">Raspberry Pi Foundation · CC BY-SA 4.0 · 中文适配</text></svg>'''


def translate_variable_references(value, names):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "VARIABLE" and isinstance(child, list) and child[0] in names:
                child[0] = names[child[0]]
            else:
                translate_variable_references(child, names)
    elif isinstance(value, list):
        if len(value) >= 3 and value[0] == 12 and value[1] in names:
            value[1] = names[value[1]]
        for child in value:
            translate_variable_references(child, names)


manifest = []
for item in ITEMS:
    slug = item["slug"]
    source = ROOT / "sources" / slug / "original.sb3"
    with zipfile.ZipFile(source) as archive:
        project = json.loads(archive.read("project.json"))
        assets = {name: archive.read(name) for name in archive.namelist() if name != "project.json"}
    before = copy.deepcopy(project)
    stage = project["targets"][0]
    names = {"time": "用时（秒）"} if slug == "boat-race" else {"lives": "剩余机会", "score": "分数", "high score": "文件内最佳", "delay": "生成间隔"}
    for target in project["targets"]:
        for variable in target["variables"].values():
            variable[0] = names.get(variable[0], variable[0])
        translate_variable_references(target["blocks"], names)
    project["monitors"] = []
    shown = ["用时（秒）"] if slug == "boat-race" else ["分数", "剩余机会", "文件内最佳"]
    for index, name in enumerate(shown):
        vid, variable = next((vid, variable) for vid, variable in stage["variables"].items() if variable[0] == name)
        project["monitors"].append(dict(id=vid, mode="default", opcode="data_variable", params={"VARIABLE": name}, spriteName=None, value=variable[1], width=0, height=0, x=10, y=10+index*26, visible=False, sliderMin=0, sliderMax=100, isDiscrete=True))
    first_flag = next(bid for bid, b in stage["blocks"].items() if b["opcode"] == "event_whenflagclicked")
    previous = first_flag
    old_next = stage["blocks"][first_flag]["next"]
    for index, name in enumerate(shown):
        vid = next(vid for vid, variable in stage["variables"].items() if variable[0] == name)
        bid = f"showcase-monitor-{index}"
        stage["blocks"][previous]["next"] = bid
        stage["blocks"][bid] = block("data_showvariable", parent=previous, fields={"VARIABLE": [name, vid]})
        previous = bid
    stage["blocks"][previous]["next"] = old_next
    stage["blocks"][old_next]["parent"] = previous
    max_layer = max(t.get("layerOrder", 0) for t in project["targets"])
    intro = sprite("玩法与来源", costume(assets, "玩法与来源", intro_svg(item), 480, 360), visible=True, layer=max_layer+2)
    intro["blocks"] = {"showcase-intro-flag": block("event_whenflagclicked", next="showcase-intro-hide", top=True), "showcase-intro-hide": block("looks_hide", parent="showcase-intro-flag")}
    footer = sprite("原作者署名", costume(assets, "原作者署名", footer_svg(), 255, 15), visible=True, layer=max_layer+1, x=100, y=-170)
    changes = ["加入绿旗前中文玩法与作者/许可画面，绿旗启动即隐藏，不延迟原游戏。", "加入画面边缘持续署名及舞台完整来源注释。", "补齐中文变量显示监视器。", "保留原地图、角色、声音、速度、碰撞颜色和计分规则。"]
    if slug == "boat-race":
        boat_target = next(t for t in project["targets"] if t["name"] == "boat")
        boat_target.update(x=-190, y=-150, direction=0, currentCostume=0)
        for b in boat_target["blocks"].values():
            if b["opcode"] == "looks_sayforsecs":
                old = b["inputs"]["MESSAGE"][1][1]
                b["inputs"]["MESSAGE"][1][1] = {"Noooooo!": "撞到岸啦，回到起点！", "YEAH!": "抵达终点！"}[old]
        changes.append("碰撞/胜利气泡中文化；文件初始小船位置与原绿旗起点一致。")
    else:
        initial = {"剩余机会": 3, "分数": 0, "文件内最佳": 0, "生成间隔": 8}
        for variable in stage["variables"].values():
            variable[1] = initial[variable[0]]
        for monitor in project["monitors"]:
            monitor["value"] = initial[monitor["params"]["VARIABLE"]]
        controller = next(t for t in project["targets"] if t["name"] == "red3roller")
        controller["blocks"]["BOlrxdw|k)6raw,j]9Jr"]["next"] = "showcase-reset-direction"
        controller["blocks"]["showcase-reset-direction"] = block("motion_pointindirection", parent="BOlrxdw|k)6raw,j]9Jr", next="GolIA@mpnC*:H7{wrc_5", inputs={"DIRECTION": [1, [8, 165]]})
        controller["blocks"]["GolIA@mpnC*:H7{wrc_5"]["parent"] = "showcase-reset-direction"
        broadcast_id = "showcase-game-over-message"
        stage["broadcasts"][broadcast_id] = "showcase-game-over"
        stage["blocks"]["FvkD=-BoeBQc6$!im=ld"]["next"] = "showcase-announce-end"
        stage["blocks"]["showcase-announce-end"] = block("event_broadcastandwait", parent="FvkD=-BoeBQc6$!im=ld", next="qRvnlb=Z26kye+LGGQGQ", inputs={"BROADCAST_INPUT": [1, [11, "showcase-game-over", broadcast_id]]})
        stage["blocks"]["qRvnlb=Z26kye+LGGQGQ"]["parent"] = "showcase-announce-end"
        end_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="280" height="60"><rect width="280" height="60" rx="15" fill="#152c43"/><text x="140" y="26" text-anchor="middle" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="19" fill="#e3edf8" font-weight="700">游戏结束</text><text x="140" y="47" text-anchor="middle" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="12" fill="#b7cada">点上方绿旗，再挑战一次！</text></svg>'''
        end = sprite("结束提示", costume(assets, "结束提示", end_svg, 280, 60), visible=False, layer=max_layer+3, x=80, y=125)
        end["blocks"] = {"showcase-end-flag": block("event_whenflagclicked", next="showcase-end-hide", top=True), "showcase-end-hide": block("looks_hide", parent="showcase-end-flag"), "showcase-end-receive": block("event_whenbroadcastreceived", next="showcase-end-show", fields={"BROADCAST_OPTION": ["showcase-game-over", broadcast_id]}, top=True), "showcase-end-show": block("looks_show", parent="showcase-end-receive")}
        project["targets"].append(end)
        changes += ["清除原文件保存的上次试玩分数；文件内最佳初值为0，游戏结束仍按原规则更新。", "绿旗将转盘方向恢复到原文件初始方向165度，保证停止后重开一致。", "机会用完后，先显示中文结束提示，再沿原脚本停止全部积木。文件内最佳仅保存在当前项目文件，非网络排行榜。"]
    project["targets"].extend([footer, intro])
    source_url = f"https://raw.githubusercontent.com/raspberrypilearning/{slug}/{item['commit']}/{item['upstream_path']}"
    license_url = f"https://github.com/raspberrypilearning/{slug}/blob/{item['commit']}/LICENSE.md"
    notes = f"原作：{item['original_title']}\n作者：Raspberry Pi Foundation\nScratch原作：{item['project']}\n官方教程：https://projects.raspberrypi.org/en/projects/{slug}\n固定来源：{source_url}\n来源提交：{item['commit']}\n原文件SHA256：{hashlib.sha256(source.read_bytes()).hexdigest()}\n许可：CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/\n上游LICENSE.md：{license_url}\n注意：上游许可正文显示Attribution 4.0，但正文链接与许可图均指向by-sa/4.0，本适配按CC BY-SA 4.0发布，并保留原LICENSE.md全文。\n适配者：TeachingOpen\n适配内容：\n" + "\n".join(changes)
    stage["comments"]["showcase-source-attribution"] = dict(blockId=None, x=20, y=900, width=620, height=460, minimized=False, text=notes)
    output = ROOT / f"{slug}.sb3"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(assets):
            info = zipfile.ZipInfo(name, (2026, 10, 14, 0, 0, 0)); info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info, assets[name])
        info = zipfile.ZipInfo("project.json", (2026, 10, 14, 0, 0, 0)); info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode())
    manifest.append(dict(**item, author="Raspberry Pi Foundation", adapted_by="TeachingOpen", tutorial=f"https://projects.raspberrypi.org/en/projects/{slug}", repository=f"https://github.com/raspberrypilearning/{slug}", source_url=source_url, license="CC BY-SA 4.0", license_url="https://creativecommons.org/licenses/by-sa/4.0/", upstream_license_file=license_url, license_text_preserved=f"sources/{slug}/LICENSE.md", license_note="Upstream text says Attribution 4.0, while its hyperlink and badge point to BY-SA 4.0. This adaptation uses the more specific BY-SA 4.0 terms.", source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), file=output.name, sha256=hashlib.sha256(output.read_bytes()).hexdigest(), bytes=output.stat().st_size, extensions=project.get("extensions", []), cloud_variables=[], adaptations=changes, upstream_target_count=len(before["targets"]), adapted_target_count=len(project["targets"])))
    cover=ROOT/"covers"/f"{slug}.png"
    if cover.exists():
        manifest[-1].update(cover=f"covers/{slug}.png", cover_sha256=hashlib.sha256(cover.read_bytes()).hexdigest(), cover_dimensions=[960,720], cover_source="Screenshot of the actual TeachingOpen Scratch player stage before the green flag.")
(ROOT/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
print(json.dumps([{k:item[k] for k in ["slug", "file", "sha256", "bytes"]} for item in manifest], ensure_ascii=False, indent=2))
