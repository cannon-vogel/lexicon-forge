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

# Second-pass teaching overrides. These replace technically valid but misleading,
# circular, overly niche, or morphology-only dictionary glosses with concise,
# answer-safe definitions suitable for learning and retrieval practice.
DEFINITION_OVERRIDES.update({
    "abettor": "A person who assists, encourages, or instigates wrongdoing.",
    "abrogative": "Serving to repeal, cancel, or abolish a law, rule, or agreement.",
    "acmes": "Highest points, peak stages, or culminations.",
    "adroitly": "With skill, cleverness, and dexterity.",
    "affecter": "A person who pretends to possess a quality, attitude, or knowledge they do not genuinely have.",
    "agglomerations": "Masses or clusters formed by gathering separate things together.",
    "allayed": "Calmed, relieved, or made less intense.",
    "alluvions": "Deposits or additions of sediment left by flowing water.",
    "ambulated": "Walked or moved about on foot.",
    "amusingness": "The quality of being entertaining, funny, or enjoyable.",
    "anaphoric": "Referring back to an earlier word, phrase, or idea in language.",
    "apotheoses": "Highest or idealized culminations; also elevations of people to divine or exalted status.",
    "approbated": "Approved, sanctioned, or officially authorized.",
    "asininity": "Extreme foolishness or stupidity.",
    "assuaged": "Made pain, distress, hunger, fear, or another unpleasant feeling less intense.",
    "bandoleer": "An ammunition belt worn across the shoulder, with loops or pockets for cartridges.",
    "besotting": "Making someone foolish, stupefied, or excessively infatuated.",
    "bifurcation": "A division into two branches, parts, or paths.",
    "blandishments": "Flattering or coaxing words and actions intended to persuade.",
    "blitheness": "Cheerful lightheartedness or carefree happiness.",
    "bugaboo": "Something that causes persistent fear, worry, or annoyance; originally an imaginary frightening creature.",
    "cairn": "A deliberately piled mound of stones used as a marker, memorial, or landmark.",
    "canniness": "Shrewdness, practical judgment, and careful cleverness.",
    "cask": "A large barrel-shaped container for storing liquids, especially wine, beer, or spirits.",
    "catatonia": "A neuropsychiatric state marked by severe abnormalities of movement, responsiveness, or behavior, sometimes including immobility or mutism.",
    "causticity": "Biting sharpness or severity, especially in speech or humor; chemically, corrosiveness.",
    "cherub": "An angelic being; in Western art, often shown as a winged child or child's face.",
    "chiasm": "A crossing or X-shaped arrangement, especially of anatomical structures such as nerves.",
    "cogitation": "Deep thought, reflection, or careful consideration.",
    "concoction": "A mixture made by combining several ingredients, sometimes improvised or unusual.",
    "confidentialness": "The quality of being private, secret, or intended to be kept from others.",
    "consubstantiation": "A theological doctrine that Christ's body and blood coexist with the bread and wine of the Eucharist.",
    "contrastively": "In a way that emphasizes a difference or contrast.",
    "corroder": "A person, substance, or process that gradually wears away or damages material by chemical action.",
    "courter": "A person seeking someone's affection, romantic interest, or marriage.",
    "covenantal": "Relating to a formal covenant, especially a solemn religious agreement or promise.",
    "crosstie": "A transverse beam supporting railroad rails and holding them at the correct spacing.",
    "cryonic": "Relating to preservation at extremely low temperatures, especially of bodies or biological material.",
    "cudgels": "Short, heavy clubs used as weapons; as a verb, strikes or beats with such a club.",
    "daystar": "The sun; in older or poetic usage, sometimes a bright morning star.",
    "deluges": "Floods or overwhelms with a very large amount; as a noun, large floods or overwhelming quantities.",
    "demureness": "Reserved, modest, or quietly composed behavior or appearance.",
    "detente": "A relaxation of tension or hostility, especially between countries.",
    "determinativeness": "The quality of being decisive, conclusive, or able to settle an issue.",
    "discomposing": "Causing someone to lose calm or composure; unsettling.",
    "doggedness": "Persistent determination and refusal to give up.",
    "downing": "The act of bringing something down, defeating it, or consuming a drink quickly.",
    "doughtiness": "Courage, toughness, and determined bravery.",
    "ducat": "A historic European gold or silver coin; by extension, money.",
    "elfin": "Small, delicate, mischievous, or otherwise suggestive of an elf.",
    "enspheres": "Surrounds or encloses something as if within a sphere.",
    "environs": "The surrounding area or nearby surroundings of a place.",
    "equitableness": "Fairness and impartiality.",
    "euphoniousness": "Pleasantness or smoothness of sound.",
    "exceptionably": "In an objectionable, questionable, or open-to-criticism manner.",
    "exchequer": "A treasury or supply of public funds, especially in British government usage.",
    "exertive": "Requiring or involving physical or mental effort.",
    "expiatory": "Intended to make amends, atone for wrongdoing, or remove guilt.",
    "extractive": "Serving to remove, draw out, or obtain something from a source.",
    "facsimile": "An exact or very close copy or reproduction of something.",
    "federacy": "A political union in which constituent regions retain substantial autonomy.",
    "flaunter": "A person who ostentatiously displays possessions, qualities, or achievements.",
    "flyweight": "A very light weight class in boxing and other combat sports; more generally, something very light or minor.",
    "foibles": "Minor weaknesses, quirks, or character flaws.",
    "foliation": "Arrangement into layers or leaflike structures; in geology, the planar layering or alignment of minerals in rock.",
    "forbiddingness": "An intimidating, threatening, or unwelcoming quality.",
    "forwent": "Did without, gave up, or chose not to have something.",
    "fussbudgety": "Fussy and overly concerned with minor or trivial details.",
    "gelatinization": "The process of becoming gelatinous; especially the thickening that occurs when starch granules absorb water and swell with heat.",
    "gendarme": "A police officer, especially a member of a national gendarmerie in France or another French-speaking country.",
    "genteel": "Polite, refined, and respectable in manner or appearance, sometimes in an affected way.",
    "gorger": "A person who eats greedily or excessively.",
    "greenroom": "A room in a theater, studio, or venue where performers wait before or after appearing.",
    "hammy": "Overacted, exaggerated, or theatrically showy.",
    "heap": "A pile or mound of things placed or thrown together; informally, a large amount.",
    "iconoclastically": "In a way that challenges or attacks established beliefs, traditions, or revered institutions.",
    "implacability": "The quality of being impossible to appease, soften, or reconcile.",
    "individualizer": "Something that distinguishes one person or thing from others or treats it as a distinct individual.",
    "ingenuousness": "Openness, sincerity, and freedom from deceit or guile.",
    "insectivorous": "Feeding on insects; insect-eating.",
    "instillation": "The gradual introduction of a liquid drop by drop, or the gradual introduction of an idea or attitude.",
    "intercessor": "A person who intervenes or pleads on behalf of another.",
    "invidiousness": "The quality of being unfairly discriminatory, offensive, or likely to provoke resentment.",
    "invitingly": "In an attractive, welcoming, or tempting way.",
    "jaunty": "Lively, cheerful, self-confident, and stylish in manner or appearance.",
    "knave": "A dishonest or unscrupulous man; historically, also the jack in a deck of playing cards.",
    "layback": "A backward-leaning position or maneuver; in climbing, a technique that uses opposing pulls with the hands and feet.",
    "lineally": "In a direct line of descent from an ancestor.",
    "malefactions": "Crimes, offenses, or evil deeds.",
    "matchlock": "An early firearm ignition mechanism that used a slow-burning match to ignite the gunpowder.",
    "mound": "A raised heap or rounded mass of earth, stones, or other material.",
    "modularity": "The quality of being built from separate parts that can be combined, replaced, or used independently.",
    "mulatto": "A dated and often offensive historical term for a person of mixed Black and white ancestry.",
    "obdurateness": "Stubborn refusal to change one's opinion, attitude, or course of action.",
    "operand": "A value or quantity on which a mathematical or logical operation is performed.",
    "orb": "A spherical object or globe; especially a round celestial body or ceremonial sphere.",
    "owlishly": "In a solemn, observant, or supposedly wise-looking manner.",
    "patchouli": "A fragrant tropical plant and the strong earthy-scented oil or perfume made from its leaves.",
    "peccadilloes": "Minor faults, offenses, or sins.",
    "persnickety": "Fussy and excessively concerned with small details.",
    "pertinacity": "Persistent determination; stubborn tenacity.",
    "polestar": "A star near a celestial pole; figuratively, a guiding principle, ideal, or standard.",
    "presaging": "Indicating or warning that something is likely to happen in the future; foreshadowing.",
    "pressmark": "A mark identifying a printer or publisher; in libraries, a shelf or call mark identifying a book's location.",
    "pronominally": "In the manner or grammatical function of a pronoun.",
    "putatively": "According to what is generally supposed or believed, though not necessarily proved.",
    "pyrrhic": "Achieved at such great cost that the success or victory is barely worthwhile.",
    "rapport": "A close, harmonious relationship marked by mutual understanding and easy communication.",
    "recallable": "Able to be remembered, retrieved, or called back.",
    "receptivity": "Willingness or ability to receive ideas, impressions, signals, or influences.",
    "redolence": "A noticeable fragrance or an evocative quality that strongly suggests or recalls something.",
    "reduplicative": "Involving repetition of all or part of a word, sound, or grammatical form.",
    "retrogressive": "Moving backward or returning to an earlier, less advanced state.",
    "ribald": "Vulgar, indecent, or humorously coarse in language or behavior.",
    "scruffiest": "Most untidy, shabby, or unkempt.",
    "scurrilousness": "The quality of being grossly abusive, defamatory, or vulgarly insulting.",
    "sententiousness": "A tendency to speak or write in brief, moralizing, self-important statements.",
    "shrewdness": "Sharp practical judgment and an ability to understand situations quickly.",
    "shoofly": "A term used for several things associated with shooing flies, including a swinging fly-deterrent; in U.S. food culture, also a molasses crumb pie.",
    "sigmoid": "S-shaped; especially describing an S-shaped curve, function, or anatomical structure.",
    "skiffle": "A style of folk-influenced popular music, especially associated with 1950s Britain and simple or improvised instruments.",
    "slangy": "Containing or characterized by frequent informal slang.",
    "somnambulistic": "Relating to sleepwalking or resembling the automatic behavior of a sleepwalker.",
    "stoutness": "The quality of being sturdy, strong, thick, or heavily built.",
    "sump": "A pit, basin, or low reservoir where liquid collects, especially in drainage, machinery, or mining systems.",
    "sumptuousness": "Richness, luxury, or magnificence.",
    "superposed": "Placed over, above, or on top of something else; superimposed.",
    "systolic": "Relating to systole, the phase when the heart contracts and pumps blood; especially the higher number in a blood-pressure reading.",
    "tangs": "Sharp, distinctive tastes or smells.",
    "temperance": "Moderation or self-restraint, especially in eating or drinking alcohol.",
    "terseness": "Brevity and concision, sometimes to the point of abruptness.",
    "tillage": "The preparation and cultivation of soil for growing crops; also land cultivated in this way.",
    "tote": "To carry or haul something; as a noun, a large carrying bag or container.",
    "traipsed": "Walked about in a casual, weary, or aimless way.",
    "turnbuckle": "A metal device with threaded ends used to adjust the tension or length of rods, cables, or wires.",
    "verisimilitude": "The appearance of being true, real, or lifelike; plausibility.",
    "waddle": "To walk with short steps while swaying from side to side.",
    "ward": "A person or place under someone's care or protection; also a division of a hospital, city, or institution.",
    "whispering": "Speaking or communicating in a very soft, quiet voice.",
    "zaniness": "Wild, eccentric, or absurdly comic behavior or quality."
})

# Concrete, saved context notes for distinctive or easily misunderstood words.
MODERN_CONTEXT_OVERRIDES = {
    "gendarme": [
        "French news or travel writing — referring to officers of the national gendarmerie.",
        "Crime, history, or fiction set in France — distinguishing gendarmes from municipal police."
    ],
    "gabardine": [
        "Vintage clothing listings — coats, suits, and trousers described by their tightly woven fabric.",
        "Tailoring and fashion history — comparing durable wool fabrics used for structured garments."
    ],
    "torpid": [
        "Nature writing — describing an animal that is unusually sluggish or inactive.",
        "Essays and reviews — describing a person, institution, or response that feels slow and inert."
    ],
    "umbra": [
        "Astronomy and eclipse coverage — naming the region of total shadow.",
        "Optics or technical diagrams — distinguishing the darkest shadow from the surrounding penumbra."
    ],
    "systolic": [
        "Medical visits and health reports — the upper number in a blood-pressure reading.",
        "Cardiology and physiology — describing the phase when the heart contracts."
    ],
    "skiffle": [
        "Music history — discussing the 1950s British scene that influenced early rock musicians.",
        "Record reviews or museum exhibits — describing folk/blues music played on simple or improvised instruments."
    ],
    "turnbuckle": [
        "Rigging, fencing, and construction — tightening cables, rods, or guy wires.",
        "Sailing and stagecraft — adjusting tension in standing rigging or suspended equipment."
    ],
    "verisimilitude": [
        "Film and book criticism — judging whether a fictional world feels convincingly real.",
        "Historical fiction and games — discussing believable detail without requiring literal accuracy."
    ]
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
    """Resolve morphology/spelling-only glosses to semantic content without naming the lemma."""
    if depth>1: return gloss
    lemma=form_reference(gloss)
    if not lemma or normalize_word(lemma)==normalize_word(gloss): return gloss
    entries,_=get_jsonl(lemma)
    if not entries: return gloss
    e,sense=pick_entry(entries,lemma,{"definitions":[],"neighbors":[]})
    base=sense_gloss(sense)
    if not base: return gloss
    if form_reference(base):
        return resolve_reference_definition(base, depth+1)
    base=clean(base)
    if base and base[-1] not in ".!?": base+="."
    return base

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

def clean_etymology_text(text):
    t=clean(text)
    if not t: return ""
    if t.startswith("Etymology tree"):
        for marker in ("Borrowed from ", "Inherited from ", "Learned borrowing from ", "Ultimately from "):
            p=t.rfind(marker)
            if p>=0:
                return t[p:]
        # Last-resort: retain only the last reasonably sentence-like "From ..." clause.
        p=t.rfind(" From ")
        if p>=0:
            return t[p+1:]
    return t

def modern_uses(word, definition, pos, labels):
    if word in MODERN_CONTEXT_OVERRIDES:
        return MODERN_CONTEXT_OVERRIDES[word]
    d=clean(definition).lower()
    rare=any(x in (labels or []) for x in ("archaic","obsolete","rare","dated","historical","literary"))
    domains=[
        (("fabric","cloth","garment","hat","tailor","wool","cotton","dress","coat","shoe"), [
            "Product listings or fashion writing — identifying materials, garments, or period styles.",
            "Museum, costume, or tailoring discussions — describing how an item is made or worn."
        ]),
        (("heart","blood","vein","lung","bone","muscle","organ","tissue","medical","disease","surgical","uterus","anatom"), [
            "Clinical or health writing — naming a body structure, symptom, condition, or measurement.",
            "Biology and anatomy coursework — using the precise technical term rather than a loose everyday substitute."
        ]),
        (("gene","chromosome","cell","protein","species","animal","bird","insect","fish","plant","biology","axon"), [
            "Biology textbooks or field guides — naming an organism, structure, or biological process.",
            "Science reporting or museum material — explaining the term to a general audience."
        ]),
        (("chemical","compound","polymer","acid","carbon","oxide","material","mineral","rock","molten"), [
            "Chemistry, geology, or materials writing — identifying a substance, structure, or process.",
            "Lab manuals and technical reports — using the precise term in a procedure or description."
        ]),
        (("law","legal","court","crime","government","vote","country","treaty","policy","trustee"), [
            "News and public-affairs writing — describing a legal, political, or diplomatic event.",
            "History, civics, or policy analysis — using a formal term with a specific institutional meaning."
        ]),
        (("money","coin","fund","debt","business","market","trade","insured","finance"), [
            "Business or financial reporting — naming a payment, fund, transaction, or economic relationship.",
            "Contracts and workplace documents — where the technical term is more precise than everyday wording."
        ]),
        (("language","speech","grammar","pronoun","word","sound","syllable","vowel","consonant"), [
            "Linguistics, grammar, or editing — analyzing how language, sounds, or references work.",
            "Literary criticism and wordplay — discussing style, diction, or structure."
        ]),
        (("music","note","sung","instrument","song","melody"), [
            "Music reviews or program notes — naming a technique, style, or musical feature.",
            "Music history and lessons — identifying the term in a score, performance, or genre discussion."
        ]),
        (("food","dish","meal","cook","meat","sauce","drink","bread","stew","herb"), [
            "Menus, cookbooks, or food journalism — naming an ingredient, dish, preparation, or flavor.",
            "Travel and restaurant writing — identifying something a reader might actually encounter on a menu."
        ]),
        (("weapon","ammunition","firearm","sword","military","soldier","battle","war"), [
            "Military history or museum labels — identifying equipment, ranks, weapons, or practices.",
            "Historical nonfiction — using the period-specific term in context."
        ]),
        (("marriage","religious","church","priest","theolog","angel","worship","divine"), [
            "Religious history or theology — naming a doctrine, office, ritual, or institution.",
            "Historical fiction or museum interpretation — vocabulary tied to a particular period or tradition."
        ]),
        (("room","building","roof","architecture","railroad","track","cable","road","land","soil"), [
            "Architecture, engineering, or property descriptions — naming a specific structure or component.",
            "Technical manuals and historical descriptions — where the exact physical term matters."
        ]),
        (("emotion","mood","behavior","person","character","foolish","stubborn","cheerful","angry","calm"), [
            "Character sketches, profiles, or reviews — describing a person's manner, mood, or behavior precisely.",
            "Fiction and narrative nonfiction — giving a more exact shade of personality than a generic adjective."
        ]),
    ]
    for keys,uses in domains:
        if any(k in d for k in keys):
            return uses
    if rare:
        return [
            "Historical fiction, older essays, or archival material — vocabulary that signals period or register.",
            "Literary criticism — discussing why an author chose an uncommon or old-fashioned term."
        ]
    p=(pos or "").lower()
    if p=="verb":
        return [
            "Narrative prose — describing a specific action more precisely than a generic verb.",
            "News, history, or essays — compressing a fairly specific action into one word."
        ]
    if p in ("adj","adjective","adv","adverb"):
        return [
            "Book reviews, profiles, or essays — giving a precise judgment about tone, behavior, or quality.",
            "Fiction and descriptive prose — adding a more exact shade of description."
        ]
    return [
        "Explanatory nonfiction — naming a specific object, idea, condition, or role without a long paraphrase.",
        "Specialist or academic writing — where a compact technical or literary term is useful."
    ]

def quiz_definition(word, definition, raw_gloss):
    """Return an answer-safe clue: no target word and no morphology-only linked lemma."""
    q=clean(definition)
    target=re.compile(r"\\b"+re.escape(word)+r"\\b",re.I)
    q=target.sub("the term",q)
    lemma=form_reference(raw_gloss)
    if lemma:
        q=re.sub(r"\\b"+re.escape(lemma)+r"\\b","",q,flags=re.I)
        q=re.sub(r"\\s+"," ",q).replace("“”","").strip(" :;,-")
    return q

def build_one(word):
    src=SOURCE.get(word, {"definitions":[],"neighbors":[],"questions":[]})
    entries,url=get_jsonl(word)
    entry,sense=pick_entry(entries,word,src)
    raw_gloss=sense_gloss(sense)
    definition=improve_definition(word,raw_gloss,sense,clean(entry.get("pos") or ""))
    if src.get("definitions"):
        # The source-test sense is authoritative for these items; dictionary gloss adds detail separately.
        source_definition=src["definitions"][0]
    else:
        source_definition=""
    ety=clean_etymology_text(entry.get("etymology_text") or "")
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
        "quizDefinition":quiz_definition(word,definition,raw_gloss),
        "rawDictionaryDefinition":raw_gloss,
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
                    "quizDefinition":(src.get("definitions") or [""])[0],
                    "rawDictionaryDefinition":"",
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
