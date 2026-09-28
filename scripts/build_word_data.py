#!/usr/bin/env python3
import csv, json, re, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
TERMS = ROOT / "terms.csv"
QUESTIONS = ROOT / "questions.csv"
OUT = ROOT / "word_data.json"
UA = "LexiconForge/1.0 static vocabulary builder (GitHub Pages educational project)"

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def tokens(s):
    return set(re.findall(r"[a-z]+", clean(s).lower())) - {
        "a","an","the","to","of","and","or","in","on","for","with","as","is","are","be","that","this","type","word","means","pick"
    }

def read_source():
    source = {}
    with QUESTIONS.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        opts = [r[f"option_{i}"] for i in range(1,6)]
        correct = [int(x) for x in r["correct_indices"].split(";") if x != ""]
        words = [opts[i] for i in correct]
        m = re.search(r"[“\"]([^”\"]+)[”\"]", r["prompt"])
        quoted = m.group(1) if m else ""
        if r["block"] == "def":
            for w in words:
                d = source.setdefault(w, {"definitions":[],"neighbors":[],"questions":[]})
                d["definitions"].append(quoted)
                d["questions"].append(int(r["question_number"]))
        elif r["block"] == "1of5":
            for w in words:
                d = source.setdefault(w, {"definitions":[],"neighbors":[],"questions":[]})
                d["neighbors"].append(quoted)
                d["questions"].append(int(r["question_number"]))
            if quoted:
                d = source.setdefault(quoted, {"definitions":[],"neighbors":[],"questions":[]})
                d["neighbors"].extend(words)
                d["questions"].append(int(r["question_number"]))
        else:
            for w in words:
                d = source.setdefault(w, {"definitions":[],"neighbors":[],"questions":[]})
                d["neighbors"].extend(x for x in words if x != w)
                d["questions"].append(int(r["question_number"]))
    for d in source.values():
        for k in ("definitions","neighbors","questions"):
            d[k] = list(dict.fromkeys(d[k]))
    return source

def read_words():
    with TERMS.open(encoding="utf-8", newline="") as f:
        return [r["term"] for r in csv.DictReader(f) if r.get("term")]

SOURCE = read_source()
WORDS = read_words()

def urls(word):
    q = urllib.parse.quote
    a = q(word[0].lower(), safe="")
    b = q(word[:2].lower(), safe="")
    w = q(word, safe="")
    return [
        f"https://kaikki.org/dictionary/English/meaning/{a}/{b}/{w}.jsonl",
        f"https://kaikki.org/dictionary/All%20languages%20combined/meaning/{a}/{b}/{w}.jsonl",
    ]

def get_jsonl(word):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
    last = None
    for url in urls(word):
        for attempt in range(3):
            try:
                r = s.get(url, timeout=(5, 18))
                if r.status_code == 404:
                    break
                r.raise_for_status()
                entries = []
                for line in r.text.splitlines():
                    line=line.strip()
                    if not line: continue
                    try:
                        obj=json.loads(line)
                    except Exception:
                        continue
                    if obj.get("lang_code") == "en" and clean(obj.get("word")).lower() == word.lower():
                        entries.append(obj)
                if entries:
                    return entries, url
            except Exception as e:
                last=e
                time.sleep(0.8*(attempt+1))
    return [], None

def sense_synonyms(sense):
    out=[]
    for x in sense.get("synonyms") or []:
        if isinstance(x, dict) and x.get("word"): out.append(clean(x["word"]))
        elif isinstance(x, str): out.append(clean(x))
    return list(dict.fromkeys(x for x in out if x))

def sense_gloss(sense):
    gs = sense.get("glosses") or sense.get("raw_glosses") or []
    if isinstance(gs, str): gs=[gs]
    for g in gs:
        g=clean(g)
        if g and "form of" not in g.lower():
            return g
    return clean(gs[0]) if gs else ""

def sense_score(word, sense, src):
    gloss=sense_gloss(sense)
    if not gloss: return -100
    score=0.0
    gt=tokens(gloss)
    for d in src.get("definitions",[]):
        dt=tokens(d)
        score += 7*len(gt & dt)
        if clean(d).lower() in gloss.lower(): score += 20
    syn={normalize_word(x) for x in sense_synonyms(sense)}
    for n in src.get("neighbors",[]):
        if normalize_word(n) in syn: score += 20
        score += 2*len(tokens(n)&gt)
    tags=set(sense.get("tags") or [])
    if "form-of" in tags or sense.get("form_of"): score -= 20
    return score

def normalize_word(s):
    return re.sub(r"[^a-z]+","",clean(s).lower())

def pick_entry(entries, word, src):
    candidates=[]
    for ei,e in enumerate(entries):
        for si,s in enumerate(e.get("senses") or []):
            gloss=sense_gloss(s)
            if gloss:
                candidates.append((sense_score(word,s,src), ei, si, e, s))
    if candidates:
        candidates.sort(key=lambda x:(x[0], -x[1], -x[2]), reverse=True)
        return candidates[0][3], candidates[0][4]
    if entries:
        return entries[0], (entries[0].get("senses") or [{}])[0]
    return {}, {}

def example_from(sense, entry):
    pools=[]
    pools.extend(sense.get("examples") or [])
    for s in entry.get("senses") or []:
        pools.extend(s.get("examples") or [])
    for ex in pools:
        if isinstance(ex, str):
            t=clean(ex); ref=""
        else:
            t=clean(ex.get("text") or ex.get("example") or "")
            ref=clean(ex.get("ref") or "")
        if 18 <= len(t) <= 500:
            return t, ref
    return "", ""

def fallback_example(word, definition, pos):
    d=clean(definition).rstrip(".")
    if not d: return ""
    p=(pos or "").lower()
    if p=="verb":
        return f"The writer chose the verb “{word}” to convey the idea “{d}.”"
    if p=="adverb":
        return f"She moved {word}, in a way that could be described as '{d}.'"
    if p=="adjective":
        return f"The description was deliberately {word}: “{d}.”"
    if p=="noun":
        return f"In context, “{word}” names or describes {d}."
    return f"In this vocabulary set, “{word}” is used for the idea “{d}.”"

def usage_labels(sense, entry):
    wanted={"archaic","obsolete","rare","dated","informal","slang","literary","historical","chiefly-uk","chiefly-us","figurative"}
    vals=[]
    for x in (sense.get("tags") or []) + (entry.get("tags") or []):
        z=clean(x).lower()
        if z in wanted and z not in vals: vals.append(z)
    return vals

def pronunciation(entry):
    ipas=[]; audio=""
    for s in entry.get("sounds") or []:
        ipa=clean(s.get("ipa") if isinstance(s,dict) else "")
        if ipa and ipa not in ipas: ipas.append(ipa)
        if isinstance(s,dict) and not audio:
            audio=s.get("mp3_url") or s.get("ogg_url") or ""
    return ipas[:3], audio

def related_words(entry, sense):
    vals=[]
    for key in ("synonyms","related","derived","antonyms"):
        objs=(sense.get(key) or []) + (entry.get(key) or [])
        for x in objs:
            w=clean(x.get("word") if isinstance(x,dict) else x)
            if w and w not in vals: vals.append(w)
    return vals[:12]

def modern_uses(word, definition, pos, labels):
    d=clean(definition).rstrip(".")
    p=(pos or "").lower()
    rare=any(x in (labels or []) for x in ("archaic","obsolete","rare","dated","historical","literary"))
    if rare:
        first=f"Historical or literary writing — “{word}” can add period flavor when the context matches its sense: {d}."
    else:
        first=f"News, essays, or explanatory writing — “{word}” is useful when you want a precise way to express: {d}."
    if p=="verb":
        second=f"Work or school — use “{word}” when describing an action or process rather than a vague verb like “do” or “make happen.”"
        third=f"Conversation or storytelling — it can sharpen a sentence about someone actively doing something connected to this meaning."
    elif p in ("adj","adjective"):
        second=f"Work or school — use “{word}” to characterize a person, situation, argument, or result more precisely."
        third=f"Conversation or storytelling — it works well as a vivid descriptor when the ordinary adjective feels too broad."
    elif p=="adverb":
        second=f"Work or school — use “{word}” to specify how an action happens, especially when manner or speed matters."
        third=f"Conversation or storytelling — it can make movement, speech, or behavior feel more exact and visual."
    else:
        second=f"Work or school — it can name a concept, object, condition, or role more precisely than a longer paraphrase."
        third=f"Conversation, reading, or storytelling — recognizing “{word}” helps when a writer chooses a compact or specialized noun for this idea."
    return [first, second, third]

def build_one(word):
    src=SOURCE.get(word, {"definitions":[],"neighbors":[],"questions":[]})
    entries,url=get_jsonl(word)
    entry,sense=pick_entry(entries,word,src)
    definition=sense_gloss(sense)
    if src.get("definitions"):
        # The source-test sense is authoritative for these items; dictionary gloss adds detail separately.
        source_definition=src["definitions"][0]
    else:
        source_definition=""
    ety=clean(entry.get("etymology_text") or "")
    ex,exref=example_from(sense,entry)
    pos=clean(entry.get("pos") or "")
    ipas,audio=pronunciation(entry)
    labels=usage_labels(sense,entry)
    if not definition:
        definition=source_definition or (("Closely related to "+", ".join(src.get("neighbors",[])[:3])) if src.get("neighbors") else "")
    if not ex:
        ex=fallback_example(word,source_definition or definition,pos)
    return word,{
        "word":word,
        "definition":definition,
        "sourceDefinition":source_definition,
        "partOfSpeech":pos,
        "etymology":ety,
        "example":ex,
        "exampleCitation":exref,
        "ipa":ipas,
        "audio":audio,
        "synonyms":sense_synonyms(sense)[:8],
        "related":related_words(entry,sense),
        "usageLabels":labels,
        "sourceNeighbors":src.get("neighbors",[]),
        "courseSynonyms":src.get("neighbors",[]),
        "courseCue":source_definition,
        "modernUses":modern_uses(word, definition, pos, labels),
        "sourceQuestions":src.get("questions",[]),
        "kaikkiUrl":url or "",
        "entryAvailable":bool(entries),
    }

def main():
    data={}
    failures=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(build_one,w):w for w in WORDS}
        done=0
        for fut in as_completed(futs):
            w=futs[fut]
            try:
                word,row=fut.result(); data[word]=row
                if not row["entryAvailable"]: failures.append(word)
            except Exception as e:
                failures.append(w)
                src=SOURCE.get(w,{})
                data[w]={
                    "word":w,"definition":(src.get("definitions") or [""])[0],
                    "sourceDefinition":(src.get("definitions") or [""])[0],
                    "partOfSpeech":"","etymology":"",
                    "example":fallback_example(w,(src.get("definitions") or [""])[0],""),
                    "exampleCitation":"","ipa":[],"audio":"","synonyms":[],"related":[],
                    "usageLabels":[],"sourceNeighbors":src.get("neighbors",[]),
                    "courseSynonyms":src.get("neighbors",[]),
                    "courseCue":(src.get("definitions") or [""])[0],
                    "modernUses":modern_uses(w,(src.get("definitions") or [""])[0],"",[]),
                    "sourceQuestions":src.get("questions",[]),"kaikkiUrl":"","entryAvailable":False
                }
            done+=1
            if done%25==0: print(f"{done}/{len(WORDS)}")
    ordered={w:data[w] for w in WORDS}
    OUT.write_text(json.dumps({
        "generated":"static-build",
        "source":"Kaikki.org / Wiktextract (Wiktionary-derived), plus TakeTest source cues",
        "count":len(ordered),
        "words":ordered
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    core=[w for w in SOURCE if w in ordered]
    cov={
      "all":len(WORDS),
      "entries":sum(1 for x in ordered.values() if x["entryAvailable"]),
      "definitions":sum(1 for x in ordered.values() if x["definition"]),
      "etymologies":sum(1 for x in ordered.values() if x["etymology"]),
      "examples":sum(1 for x in ordered.values() if x["example"]),
      "core":len(core),
      "core_entries":sum(1 for w in core if ordered[w]["entryAvailable"]),
      "core_etymologies":sum(1 for w in core if ordered[w]["etymology"]),
      "core_examples":sum(1 for w in core if ordered[w]["example"]),
      "failures":failures
    }
    (ROOT/"word_data_stats.json").write_text(json.dumps(cov,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(cov,indent=2))

if __name__=="__main__":
    main()
