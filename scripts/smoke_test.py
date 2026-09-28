#!/usr/bin/env python3
import csv, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

with (ROOT/"questions.csv").open(encoding="utf-8",newline="") as f:
    questions=list(csv.DictReader(f))
with (ROOT/"terms.csv").open(encoding="utf-8",newline="") as f:
    terms=list(csv.DictReader(f))
data=json.loads((ROOT/"word_data.json").read_text(encoding="utf-8"))
stats=json.loads((ROOT/"word_data_stats.json").read_text(encoding="utf-8"))
words=data["words"]
app=(ROOT/"app.js").read_text(encoding="utf-8")
index=(ROOT/"index.html").read_text(encoding="utf-8")

assert len(questions)==108, len(questions)
assert len(terms)==537, len(terms)
assert data["count"]==537 and len(words)==537
assert stats.get("failures")==[], stats.get("failures",[])[:10]
unavailable=[w for w,d in words.items() if not d.get("entryAvailable")]
assert not unavailable, unavailable[:10]

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
missing_uses=[w for w,d in words.items() if len(d.get("modernUses") or [])<2]
missing_course_fields=[w for w,d in words.items() if "courseSynonyms" not in d or "courseCue" not in d]
missing_quiz=[w for w,d in words.items() if not str(d.get("quizDefinition","")).strip()]
assert not missing_defs, missing_defs[:10]
assert not missing_examples, missing_examples[:10]
assert not missing_uses, missing_uses[:10]
assert not missing_course_fields, missing_course_fields[:10]
assert not missing_quiz, missing_quiz[:10]

# Every card must carry its full learner-facing material locally.
missing_origins=[w for w,d in words.items() if not str(d.get("etymologyBrief","")).strip()]
bad_origins=[]
bad_encounters=[]
placeholder_phrases=re.compile(r"(?:the word .+ in context|rather than wait|the problem|described in the article| on display[”"]?$)",re.I)
morph_only=re.compile(r"^(?:From|Built from)\s+\S+\s+\+\s+-[^.]+\.$",re.I)
for w,d in words.items():
    brief=str(d.get("etymologyBrief","")).strip()
    if len(brief)>520 or "Etymology tree" in brief or morph_only.match(brief):
        bad_origins.append((w,brief))
    if re.search(r"No reliable deeper origin|deeper origin is not stated",brief,re.I):
        bad_origins.append((w,brief))
    encounters=d.get("encounters") or []
    if len(encounters)<2:
        bad_encounters.append((w,encounters))
        continue
    nw=re.sub(r"[^a-z0-9]","",w.lower())
    for e in encounters[:2]:
        place=str(e.get("place","")).strip()
        phrase=str(e.get("phrase","")).strip()
        np=re.sub(r"[^a-z0-9]","",phrase.lower())
        if not place or not phrase or placeholder_phrases.search(phrase) or (nw and nw not in np):
            bad_encounters.append((w,e))
assert not missing_origins, missing_origins[:10]
assert not bad_origins, bad_origins[:15]
assert not bad_encounters, bad_encounters[:15]

# Quick-check clues must not leak the answer or a linked conjugation/base form.
answer_leaks=[]
for w,d in words.items():
    q=str(d.get("quizDefinition",""))
    if re.search(r"\b"+re.escape(w)+r"\b",q,re.I):
        answer_leaks.append((w,"answer",q))
    lemma=str(d.get("linkedLemma","") or "")
    if lemma and re.search(r"\b"+re.escape(lemma)+r"\b",q,re.I):
        answer_leaks.append((w,"lemma:"+lemma,q))
assert not answer_leaks, answer_leaks[:15]

# Definition audit across all 537 entries: no context-dependent secondary glosses
# and no unresolved morphology-only definitions.
bad_defs=[]
formula=re.compile(r"^(plural|comparative|superlative|simple past|past participle|present participle|third-person singular|alternative (?:form|spelling)|(?:us|uk) standard (?:form|spelling))",re.I)
for w,d in words.items():
    definition=str(d.get("definition","")).strip()
    if re.match(r"^(?:a|an|the)?\s*similar\b",definition,re.I):
        bad_defs.append((w,definition))
    if definition.endswith(":"):
        bad_defs.append((w,definition))
    if formula.match(definition) and ":" not in definition:
        bad_defs.append((w,definition))
assert not bad_defs, bad_defs[:15]

# The known high-risk polysemous items must stay on useful modern/common senses.
assert words["torpid"]["definition"].startswith("Sluggish")
assert words["gendarme"]["definition"].startswith("A police officer")
assert words["cask"]["definition"].startswith("A large barrel-shaped")
assert "heart contracts" in words["systolic"]["definition"]
assert "folk-influenced popular music" in words["skiffle"]["definition"]
assert words["umbra"]["definition"].startswith("A shadow")
assert words["natty"]["definition"].startswith("Neat, stylish")
assert "woolen cloth" in words["gabardine"]["definition"]
assert "making and selling of hats" in words["millinery"]["definition"]
assert "directed traffic" in words["gendarme"]["example"]
assert "oak cask" in words["cask"]["example"]
assert "blood pressure" in words["systolic"]["example"]
assert "guitar" in words["skiffle"]["example"]
assert "gens d’armes" in words["gendarme"]["etymologyBrief"]
assert "pith" in words["pithiness"]["etymologyBrief"].lower()
assert words["gendarme"]["encounters"][0]["place"].startswith("French news")
assert "gendarme" in words["gendarme"]["encounters"][0]["phrase"].lower()
assert "wristlock" in words["wristlock"]["encounters"][0]["phrase"].lower()

# Modern-use prompts should be concrete context notes: a setting plus a short explanation.
bad_uses=[]
for w,d in words.items():
    for u in (d.get("modernUses") or []):
        if len(u)>210 or " — " not in u:
            bad_uses.append((w,u))
assert not bad_uses, bad_uses[:15]

# Regression check for the user's first visible lesson card.
bond=words["bondman"]
assert len(bond["definition"])>10 and bond["definition"].strip().lower()!="slave"
assert bond.get("courseCue")=="slave"
assert len(bond.get("modernUses") or [])>=2

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
print("  537 definitions + examples + >=2 concrete encounter contexts")
print("  537 locally bundled learner etymologies")
print("  definition audit: no unresolved/secondary-sense patterns")
print("  encounter cards have specific source types + usable phrases")
print("  no bare conjugation/suffix-only etymologies")
print("  7-pigeon shop with full-XP mythic bird")
print("  no runtime dictionary API dependency")
print("  quick-check empty-class regression guarded")
print("  all quiz clues are answer-safe and lemma-safe")
print("  license + third-party notice + subtle disclaimer present")
