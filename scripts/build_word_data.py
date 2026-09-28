#!/usr/bin/env python3
import csv, json, re, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
# Build marker: definition-audit final
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

# Curated overrides for words where an automatically selected Wiktionary sense can be
# technically valid but pedagogically misleading or unusually niche.
DEFINITION_OVERRIDES = {
    "apotheoses": "Plural of apotheosis: the highest point or idealized culmination of something; also the elevation of a person to divine or exalted status.",
    "ax": "An axe: a tool with a heavy bladed head on a handle, used especially for chopping wood; figuratively, a dismissal or cut.",
    "conglomerate": "A group made up of unlike parts; in business, a corporation composed of several different companies.",
    "delineation": "A description, outline, or representation that clearly shows the form, features, or boundaries of something.",
    "evanescent": "Quickly fading or disappearing; short-lived or fleeting.",
    "excursive": "Wandering or digressive; tending to stray from a direct course or main topic.",
    "exultancy": "A state or expression of triumphant joy; exultation.",
    "millinery": "The making and selling of hats, especially women's hats; also hats collectively.",
    "morass": "Literally, soft marshy ground; figuratively, a complicated or confusing situation that is difficult to escape.",
    "natty": "Neat, stylish, and smart in appearance or dress.",
    "perambulation": "The act of walking around or through a place; a stroll, walk, or walking tour.",
    "polemics": "Strong written or spoken arguments attacking a position or opponent; controversial debate.",
    "ramified": "Divided or spread into branches or subdivisions; extensively branched.",
    "sinuousness": "The quality of curving, winding, or bending in a smooth, wave-like way.",
    "soya": "Soy or soybean, especially in British usage; also food or products made from soybeans.",
    "torpid": "Sluggish, inactive, or lacking energy; moving or responding slowly.",
    "trusteeship": "The office, responsibility, or guardianship of a trustee: managing property or affairs on behalf of another.",
    "umbra": "A shadow, especially the darkest central part of a shadow, such as the region of total shadow in an eclipse.",
    "anachronously": "In a way that is chronologically out of place or assigned to the wrong historical period.",
    "awhirl": "Spinning or whirling; in rapid circular motion.",
    "bountifully": "In a generous or abundant manner; plentifully.",
    "caddishly": "In a rude, selfish, or dishonorable manner.",
    "changefulness": "The quality of changing often; variability or instability.",
    "concretive": "Tending to form, promote, or produce a concretion or solid mass.",
    "decantate": "To pour a liquid carefully from one container into another, usually leaving sediment behind; to decant.",
    "deflowerer": "A person who deflowers another; historically, a person who takes another person's virginity.",
    "disapprobative": "Expressing disapproval or condemnation.",
    "extoller": "A person who praises someone or something very highly.",
    "farcically": "In an absurd, ridiculous, or farce-like way.",
    "harnesser": "A person or device that harnesses, controls, or puts something to use.",
    "imputable": "Able to be attributed or assigned to a person, cause, or source.",
    "inculcator": "A person who teaches or impresses an idea through repeated instruction.",
    "inconsistent": "Not remaining the same in behavior, quality, or logic; containing contradictions or varying unpredictably.",
    "munificently": "In an exceptionally generous or lavish manner.",
    "pianoforte": "A piano; the full historical name for the keyboard instrument.",
    "plaintively": "In a sad, mournful, or pleading manner.",
    "prevaricator": "A person who avoids telling the truth directly by being evasive or misleading.",
    "seizer": "A person or thing that takes hold of, captures, or confiscates something.",
    "tonally": "In relation to tone, pitch, or a tonal system.",
    "unwontedly": "In an unusual or unaccustomed way.",
    "usherette": "A female usher, especially one who shows patrons to seats in a theater or cinema; the term is now dated."
}

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

def normalize_word(s):
    return re.sub(r"[^a-z]+","",clean(s).lower())

FORM_PATTERNS = [
    r"^(?:plural|comparative|superlative)(?: form)? of\s+([^:.;]+?)[.]?$",
    r"^(?:simple past(?: and past participle)?|past participle|present participle(?: and gerund)?|third-person singular simple present indicative) of\s+([^:.;]+?)[.]?$",
    r"^alternative (?:form|spelling|letter-case form) of\s+([^:.;]+?)(?:\s*\([^)]*\))?[.]?$",
    r"^(?:us|uk) standard (?:form|spelling) of\s+([^:.;]+?)[.]?$",
]
def form_reference(gloss):
    g=clean(gloss).lower()
    for pat in FORM_PATTERNS:
        m=re.match(pat,g,re.I)
        if m:
            return clean(m.group(1)).strip(" .")
    return ""

def clarity_penalty(gloss):
    g=clean(gloss)
    low=g.lower()
    p=0
    if len(g)<12: p+=18
    elif len(g)<24: p+=7
    if g.endswith(":"): p+=25
    if re.match(r"^(a|an|the)?\s*similar\b",low): p+=35
    if re.match(r"^(alternative|variant) (form|spelling)\b",low): p+=55
    if re.match(r"^(plural|comparative|superlative|simple past|past participle|present participle|third-person)",low): p+=55
    if re.search(r"\b(?:same as|see also|see )\b",low): p+=20
    return p

def sense_score(word, sense, src, entry=None, ei=0, si=0):
    gloss=sense_gloss(sense)
    if not gloss: return -1000
    score=24.0-clarity_penalty(gloss)
    gt=tokens(gloss)
    # Source cues distinguish the intended sense, but never substitute for a real definition.
    for d in src.get("definitions",[]):
        dt=tokens(d)
        score += 3.5*len(gt & dt)
        if clean(d).lower() in gloss.lower(): score += 8
    syn={normalize_word(x) for x in sense_synonyms(sense)}
    for n in src.get("neighbors",[]):
        if normalize_word(n) in syn: score += 8
        score += 1.2*len(tokens(n)&gt)
    tags={clean(x).lower() for x in (sense.get("tags") or [])}
    if "form-of" in tags or sense.get("form_of"): score -= 45
    if any(t in tags for t in ("obsolete","archaic","rare","dated","historical")): score -= 12
    if sense.get("examples"): score += 5
    if sense_synonyms(sense): score += 3
    # Mildly favor earlier dictionary senses only after clarity/commonness checks.
    score -= 0.35*ei + 0.12*si
    return score

def pick_entry(entries, word, src):
    candidates=[]
    for ei,e in enumerate(entries):
        for si,sense in enumerate(e.get("senses") or []):
            gloss=sense_gloss(sense)
            if gloss:
                candidates.append((sense_score(word,sense,src,e,ei,si), ei, si, e, sense))
    if candidates:
        candidates.sort(key=lambda x:x[0],reverse=True)
        return candidates[0][3], candidates[0][4]
    if entries:
        return entries[0], (entries[0].get("senses") or [{}])[0]
    return {}, {}

def resolve_reference_definition(gloss, depth=0):
    if depth>1: return gloss
    lemma=form_reference(gloss)
    if not lemma or normalize_word(lemma)==normalize_word(gloss): return gloss
    entries,_=get_jsonl(lemma)
    if not entries: return gloss
    e,s=pick_entry(entries,lemma,{"definitions":[],"neighbors":[]})
    base=sense_gloss(s)
    if not base or form_reference(base): return gloss
    low=clean(gloss).lower()
    if low.startswith("plural"):
        lead=f"Plural of “{lemma}”"
    elif low.startswith("superlative"):
        lead=f"Superlative form of “{lemma}”"
    elif low.startswith("comparative"):
        lead=f"Comparative form of “{lemma}”"
    elif "past" in low:
        lead=f"Past-tense form of “{lemma}”"
    elif "participle" in low:
        lead=f"Participle of “{lemma}”"
    elif "alternative" in low or "standard" in low or "spelling" in low:
        lead=f"Variant of “{lemma}”"
    else:
        lead=f"Form of “{lemma}”"
    return f"{lead}: {base[0].lower()+base[1:] if base else base}"

def improve_definition(word, gloss, sense, pos):
    if word in DEFINITION_OVERRIDES:
        return DEFINITION_OVERRIDES[word]
    g=clean(gloss).strip()
    if not g: return g
    if form_reference(g):
        return resolve_reference_definition(g)
    # Secondary senses that depend on a missing antecedent are not self-contained.
    g=re.sub(r"^A similar\s+", "A ", g, flags=re.I)
    g=re.sub(r"^An? form of\s+", "", g, flags=re.I)
    if g and g[-1] not in ".!?": g+="."
    return g

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
    d=clean(definition).lower()
    rare=any(x in (labels or []) for x in ("archaic","obsolete","rare","dated","historical","literary"))
    domains=[
        (("fabric","cloth","garment","hat","clothing","wool","cotton","dress","coat"), ["Clothing or product descriptions","Tailoring and textile discussions","Fashion history or vintage catalogs"]),
        (("anatom","body","bone","muscle","organ","tissue","medical","disease","surgical"), ["Medical or anatomy writing","Clinical or health discussions","Biology coursework"]),
        (("food","dish","meal","cook","meat","sauce","drink","bread"), ["Menus and food writing","Cooking discussions","Restaurant or travel descriptions"]),
        (("law","legal","crime","court","government","politic"), ["News and public-affairs writing","Legal or policy discussions","History and civics coursework"]),
        (("plant","animal","bird","insect","fish","species","genus"), ["Biology or field guides","Nature writing","Museum or science descriptions"]),
        (("word","language","speech","grammar","letter","sound","linguistic"), ["Language and linguistics","Editing or literary analysis","Vocabulary and wordplay"]),
        (("money","trade","business","market","economic","finance"), ["Business or finance writing","News reporting","Workplace discussions"]),
        (("emotion","feeling","mood","behavior","person","character"), ["Character descriptions","Psychology or social writing","Conversation and storytelling"]),
        (("building","architecture","room","house","wall","road"), ["Architecture or design","Property descriptions","Historical or travel writing"]),
    ]
    for keys,uses in domains:
        if any(k in d for k in keys):
            return uses
    if rare:
        return ["Historical writing","Literary or period dialogue","Older texts and archives"]
    p=(pos or "").lower()
    if p=="verb":
        return ["Essays and nonfiction","Work or academic writing","Storytelling and dialogue"]
    if p in ("adj","adjective","adv","adverb"):
        return ["Precise description","Literary or analytical writing","Conversation and storytelling"]
    return ["Essays and nonfiction","Academic or specialist writing","Literary and descriptive prose"]

def build_one(word):
    src=SOURCE.get(word, {"definitions":[],"neighbors":[],"questions":[]})
    entries,url=get_jsonl(word)
    entry,sense=pick_entry(entries,word,src)
    definition=improve_definition(word,sense_gloss(sense),sense,clean(entry.get("pos") or ""))
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
        "definitionQuality":{
            "selfContained": not bool(form_reference(definition)) and not bool(re.match(r"^(?:a|an|the)?\\s*similar\\b",definition,re.I)),
            "length": len(definition),
            "clarityPenalty": clarity_penalty(definition)
        },
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
