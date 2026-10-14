"""Check source retention, asset integrity, block links and declared SB3 compatibility."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parent
results=[]
for item in json.loads((ROOT/"manifest.json").read_text()):
    source=ROOT/"sources"/item["slug"]/"original.sb3"
    final=ROOT/item["file"]
    assert hashlib.sha256(source.read_bytes()).hexdigest()==item["source_sha256"]
    assert hashlib.sha256(final.read_bytes()).hexdigest()==item["sha256"]
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(final) as new:
        assert old.testzip() is None and new.testzip() is None
        original=json.loads(old.read("project.json"))
        adapted=json.loads(new.read("project.json"))
        original_assets=[n for n in old.namelist() if n!="project.json"]
        assert all(old.read(n)==new.read(n) for n in original_assets), "Upstream media changed"
        assert adapted["extensions"]==original["extensions"]==[]
        assert all(not (len(v)>2 and v[2]) for t in adapted["targets"] for v in t["variables"].values())
        count=0
        for target in adapted["targets"]:
            blocks=target["blocks"]
            for bid,b in blocks.items():
                for link in [b.get("next"),b.get("parent")]:
                    assert link is None or link in blocks, (target["name"],bid,link)
                for value in b.get("inputs",{}).values():
                    for link in value[1:]:
                        assert not isinstance(link,str) or link in blocks, (target["name"],bid,link)
            for costume in target["costumes"]:
                raw=new.read(costume["md5ext"])
                assert hashlib.md5(raw).hexdigest()==costume["assetId"]
            for sound in target["sounds"]:
                assert sound["md5ext"] in new.namelist()
            count+=len(blocks)
        for old_target in original["targets"]:
            target=next(t for t in adapted["targets"] if t["name"]==old_target["name"])
            assert set(old_target["blocks"]).issubset(target["blocks"])
        comment=adapted["targets"][0]["comments"]["showcase-source-attribution"]["text"]
        assert all(value in comment for value in [item["project"],item["source_url"],item["tutorial"],item["source_sha256"],"Raspberry Pi Foundation","CC BY-SA 4.0"])
        result=dict(slug=item["slug"],sha256=item["sha256"],bytes=final.stat().st_size,targets=len(adapted["targets"]),blocks=count,unchanged_upstream_assets=len(original_assets),all_source_block_ids_retained=True,extension_count=0,cloud_variable_count=0,archive_crc="pass",block_references="pass",source_comment="pass")
        results.append(result)
(ROOT/"validation.json").write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(results,ensure_ascii=False,indent=2))
