#!/usr/bin/env python3
import csv, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

with (ROOT/"questions.csv").open(encoding="utf-8",newline="") as f:
    questions=list(csv.DictReader(f))
with (ROOT/"terms.csv").open(encoding="utf-8",newline="") as f:
    terms=list(csv.DictReader(f))
data=json.loads((ROOT/"word_data.json").read_text(encoding="utf-8"))
words=data["words"]
app=(ROOT/"app.js").read_text(encoding="utf-8")
index=(ROOT/"index.html").read_text(encoding="utf-8")

assert len(questions)==108, len(questions)
assert len(terms)==537, len(terms)
assert data["count"]==537 and len(words)==537

# Recompute the actual target/answer pool.
core=[]
for q in questions:
    opts=[q[f"option_{i}"] for i in range(1,6)]
    for i in [int(x) for x in q["correct_indices"].split(";") if x!=""]:
        if opts[i] not in core: core.append(opts[i])
    if q["block"]=="1of5":
        m=re.search(r'[“"]([^”"]+)[”"]',q["prompt"])
        if m and m.group(1) not in core: core.append(m.group(1))
assert len(core)==186, len(core)

missing_defs=[w for w,d in words.items() if not str(d.get("definition","")).strip()]
missing_examples=[w for w,d in words.items() if not str(d.get("example","")).strip()]
missing_uses=[w for w,d in words.items() if len(d.get("modernUses") or [])<3]
missing_course_fields=[w for w,d in words.items() if "courseSynonyms" not in d or "courseCue" not in d]
assert not missing_defs, missing_defs[:10]
assert not missing_examples, missing_examples[:10]
assert not missing_uses, missing_uses[:10]
assert not missing_course_fields, missing_course_fields[:10]

# Regression check for the user's first visible lesson card.
bond=words["bondman"]
assert len(bond["definition"])>10 and bond["definition"].strip().lower()!="slave"
assert bond.get("courseCue")=="slave"
assert len(bond.get("modernUses") or [])>=3

# Pigeon shop / habitat integration.
m=re.search(r"const PIGEONS=\[(.*?)\];\nconst ENRICH_TTL",app,re.S)
assert m, "PIGEONS catalog missing"
catalog=m.group(1)
assert len(re.findall(r"\bid:'",catalog))==7
assert "FULL_XP_MILESTONE=88794" in app
assert "price:FULL_XP_MILESTONE" in catalog
assert "renderPigeonShop" in app and "renderHabitat" in app and "buyPigeon" in app
assert 'data-view="pigeons"' in index and 'id="pigeonShop"' in index and 'id="pigeonHabitat"' in index

# Study path must remain local/static.
assert "dictionaryapi.dev/api" not in app
assert "/w/api.php" not in app

# Quick-check regression guard: adding an empty class token throws a DOMException.
assert "classList.add(ok?'selected':'')" not in app
assert "classList.add(ok?'selected':'wrong')" in app

# Licensing / disclaimer files must ship with the public build.
assert (ROOT/"LICENSE").exists()
assert (ROOT/"THIRD_PARTY_NOTICES.md").exists()
assert "Unofficial educational study tool" in index
assert 'href="THIRD_PARTY_NOTICES.md"' in index
assert 'href="LICENSE"' in index

print("Lexicon Forge smoke test passed:")
print("  108 source items")
print("  537 lexical entries")
print("  186 core targets")
print("  537 definitions + examples + >=3 modern-use ideas")
print("  7-pigeon shop with full-XP mythic bird")
print("  no runtime dictionary API dependency")
print("  quick-check empty-class regression guarded")
print("  license + third-party notice + subtle disclaimer present")
