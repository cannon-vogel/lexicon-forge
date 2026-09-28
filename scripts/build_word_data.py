#!/usr/bin/env python3
import csv, json, re, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from functools import lru_cache

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
DEFINITION_OVERRIDES.update({
    "acquiescent": "Willing to accept or agree without protest, objection, or resistance.",
    "conniption": "A sudden fit of anger, panic, or agitation.",
    "conducer": "A person, thing, or factor that helps bring about a result.",
    "covenantal": "Relating to a solemn agreement or promise, especially in a religious context.",
    "decantate": "To pour a liquid carefully into another container, usually leaving sediment behind.",
    "deflowerer": "A person who takes another person's virginity; a historical sexual term.",
    "deftly": "Skillfully, quickly, and neatly.",
    "doltish": "Stupid, clumsy, or foolish.",
    "expressible": "Able to be stated, shown, represented, or communicated.",
    "farcically": "In an absurdly comic or ridiculous way.",
    "fatigable": "Prone to becoming physically or mentally tired.",
    "gelatinization": "The process of thickening into a gel-like state, especially when starch absorbs water and is heated.",
    "gendarme": "A police officer, especially one in France or another country with a military-style national police force.",
    "harnesser": "A person or device that controls, channels, or puts something to practical use.",
    "hostelry": "An inn, hotel, or other place that provides lodging to travelers.",
    "indisposition": "A mild illness or temporary feeling of being unwell.",
    "intellection": "The mental process of understanding, reasoning, or grasping an idea.",
    "latticed": "Arranged in a crisscross framework or open grid pattern.",
    "literalism": "Strict adherence to the exact wording or surface meaning of a text, rule, or statement.",
    "meniscal": "Relating to a crescent-shaped structure, especially cartilage in a joint or the curved surface of a liquid.",
    "myelination": "The formation of an insulating fatty sheath around nerve fibers.",
    "normative": "Establishing, relating to, or conforming to standards of what ought to be.",
    "pronator": "A muscle that rotates the forearm so the palm faces downward or backward.",
    "puppyhood": "The early period of a dog's life before adulthood.",
    "pyloric": "Relating to the opening between the stomach and the small intestine.",
    "riotous": "Wildly disorderly or boisterous; also involving a public disturbance.",
    "slangy": "Using a lot of informal or colloquial language.",
    "systolic": "Relating to the phase when the heart contracts and pumps blood; especially the higher number in a blood-pressure reading.",
    "trackside": "Located beside a railroad, racetrack, or other track.",
    "usherette": "A woman whose job is to guide patrons to seats in a theater or cinema; the term is now dated."
})

DEFINITION_OVERRIDES.update({
    "adamancy": "Unyielding firmness or determination; refusal to change one's position.",
    "adenosine": "A nucleoside made of adenine and ribose that plays important roles in cellular energy transfer and signaling.",
    "anthracite": "A hard, glossy coal with a high carbon content that burns relatively cleanly.",
    "archduke": "A historical royal title associated especially with the Habsburg family, ranking below emperor or king.",
    "armistice": "An agreement between opposing sides to stop fighting, usually temporarily.",
    "bemoaning": "Expressing sorrow, regret, or complaint about something.",
    "brogue": "A sturdy perforated shoe; also a strong regional accent, especially an Irish or Scottish one.",
    "buttressed": "Strengthened or supported, literally by projecting supports or figuratively by reinforcing evidence or arguments.",
    "cabinetwork": "The craft or work of making cabinets and fine wooden furniture.",
    "carob": "A Mediterranean tree whose sweet edible pods are used as food and as a cocoa-like flavoring.",
    "chicory": "A plant whose leaves are eaten as salad and whose roasted root can flavor or substitute for coffee.",
    "coinsurance": "An insurance arrangement in which the insured pays a percentage of covered costs and the insurer pays the rest.",
    "discomposure": "Loss of calm or self-possession; agitation or embarrassment.",
    "egregious": "Outstandingly bad, shocking, or flagrant.",
    "execratory": "Expressing a curse, denunciation, or intense condemnation.",
    "hedonic": "Relating to pleasure, enjoyment, or the pursuit of pleasure.",
    "hook": "A point in a system, especially software, where behavior can be intercepted, extended, or modified.",
    "huff": "A short forceful breath or snort; also a state of offended anger.",
    "indicant": "Something that points out, indicates, or serves as a sign.",
    "kilting": "Arranging fabric into overlapping vertical pleats, as in the construction of a kilt.",
    "mendacity": "Untruthfulness or a tendency to lie.",
    "oafish": "Clumsy, stupid, or socially awkward.",
    "pithiness": "Concise, forceful expression using few words.",
    "primogenitary": "Relating to inheritance by the eldest child, traditionally the eldest son.",
    "ranginess": "The quality of being long-limbed, loosely built, or spread over a wide area.",
    "renormalize": "To adjust a quantity or model to a new normalization scale or reference, especially in mathematical physics.",
    "resurvey": "To examine, measure, or map an area again.",
    "sack": "A large bag; as a verb, to dismiss someone from a job or to plunder a captured place.",
    "stultification": "The process of making something ineffective, absurd, or intellectually dull.",
    "summate": "To add a set of quantities together.",
    "trusteeship": "Responsibility for managing property, assets, or affairs on behalf of another person or group.",
    "uncritical": "Not evaluating something carefully or questioning its assumptions or claims.",
    "vacuole": "A membrane-bound sac inside a cell used for storage, waste handling, or water balance; more generally, a small cavity."
})

DEFINITION_OVERRIDES.update({
    "ammonic": "Relating to the cornu ammonis, an older anatomical name for the hippocampal formation of the brain.",
    "ax": "A chopping tool with a heavy bladed head on a handle; figuratively, a dismissal or cut.",
    "soya": "The soybean plant or foods and products made from its beans, especially in British usage."
})

DEFINITION_OVERRIDES.update({
    "chamois": "A small goat-antelope of European mountains; also the soft leather traditionally made from its hide or a similar cleaning cloth.",
    "confirmatively": "In a way that confirms, supports, or verifies something.",
    "concretive": "Promoting the formation of a solid mass, deposit, or concretion.",
    "demurrer": "A legal objection arguing that, even if the opponent's alleged facts are true, they do not establish a legally sufficient claim.",
    "dewiness": "Fresh moisture like tiny droplets of dew; figuratively, a fresh or youthful appearance.",
    "extenuating": "Making a fault or offense seem less serious by providing mitigating circumstances.",
    "glossarist": "A person who compiles, writes, or edits a glossary.",
    "hook": "A curved device for catching or holding something; in software, a point where behavior can be intercepted, extended, or modified.",
    "impetuous": "Acting quickly and forcefully without enough thought; impulsive or rash.",
    "indiscriminate": "Done without careful selection or distinction; random, unselective, or lacking judgment.",
    "leatherhead": "A friarbird, especially an Australian honeyeater with a bare dark head.",
    "ludicrous": "So absurd, unreasonable, or incongruous as to provoke laughter.",
    "octavo": "A book format made by folding a printed sheet three times to form eight leaves, or sixteen pages.",
    "philanthropy": "The giving of money, time, or resources to promote the welfare of others or the public good.",
    "pliant": "Flexible and easily bent; figuratively, readily influenced or adaptable.",
    "reprobate": "Morally unprincipled or depraved; as a noun, a person regarded as lacking principles.",
    "roulade": "A decorative run of several musical notes sung on one syllable; also a rolled food preparation.",
    "sizzle": "To make a sharp hissing sound like food cooking on a hot surface.",
    "terrine": "A loaf-like preparation of meat, fish, or vegetables cooked and often served in a deep earthenware dish; also the dish itself.",
    "tintype": "An early photograph made as a positive image on a thin lacquered iron plate.",
    "totter": "To sway or move unsteadily as if about to fall; figuratively, to be close to collapse.",
    "uproarious": "Extremely noisy and boisterous, or extremely funny.",
    "ward": "A person under another's legal care or protection; also a division of a hospital, city, prison, or other institution."
})

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
    ],
    "cask": [
        "Wine, beer, and whisky writing — describing aging or storage in wooden barrels.",
        "Brewery and distillery tours — distinguishing cask-aged products from tank- or bottle-aged ones."
    ],
    "catatonia": [
        "Psychiatry and hospital documentation — describing a serious syndrome involving movement and responsiveness.",
        "Medical journalism — explaining why immobility or mutism can require urgent clinical assessment."
    ],
    "jaunty": [
        "Fashion or style writing — a hat, scarf, or outfit worn with cheerful confidence.",
        "Fiction and profiles — describing someone's upbeat, self-assured walk or manner."
    ],
    "allayed": [
        "News reporting — fears or concerns reduced after new evidence, reassurance, or action.",
        "Medical or personal writing — pain, anxiety, or discomfort becoming less intense."
    ],
    "acmes": [
        "History or criticism — comparing several peak periods in a career, movement, or civilization.",
        "Science and technical writing — referring to multiple maximum stages or high points."
    ],
    "pyrrhic": [
        "Politics, war, and business analysis — a win whose cost nearly cancels its benefit.",
        "Sports commentary — a victory that leaves a team too depleted to capitalize on it."
    ],
    "detente": [
        "International-relations news — a period when rival states deliberately reduce hostility.",
        "Cold War history — describing diplomatic easing without implying full friendship or alliance."
    ],
    "rapport": [
        "Therapy, interviews, and teaching — building an easy, trusting connection with another person.",
        "Workplace communication — describing a relationship where conversation feels natural and cooperative."
    ],
    "sump": [
        "Home maintenance — the basin beneath a basement sump pump that collects groundwater.",
        "Automotive and industrial systems — the low reservoir where oil or other liquid collects."
    ],
    "waddle": [
        "Nature writing — ducks, penguins, or other animals moving with short side-to-side steps.",
        "Humorous narration — describing a person walking with a pronounced swaying gait."
    ],
    "whispering": [
        "Fiction and dialogue — speech kept deliberately quiet so nearby people cannot easily hear.",
        "Voice and audio work — describing very soft vocal delivery, from stage acting to ASMR."
    ],
    "matchlock": [
        "Military history and museum labels — identifying early firearms that used a burning match for ignition.",
        "Historical fiction or reenactment — distinguishing pre-flintlock firearm technology."
    ],
    "millinery": [
        "Fashion history and costume museums — the craft and trade of designing or selling hats.",
        "Vintage shopping and theater wardrobe — specialist language for hat-making and hat departments."
    ],
    "plebiscite": [
        "Election and constitutional news — a direct public vote on a major political question.",
        "History writing — votes over borders, sovereignty, or national status."
    ],
    "morass": [
        "Political or business commentary — a figurative tangle of rules, disputes, or bureaucracy.",
        "Nature writing — literally, soft marshy ground that is difficult to cross."
    ],
    "conniption": [
        "Informal American conversation — an exaggerated burst of anger, panic, or agitation.",
        "Humorous fiction — describing someone dramatically losing their composure."
    ],
    "tote": [
        "Retail and everyday speech — carrying groceries, gear, or a large tote bag.",
        "Warehousing and logistics — a reusable plastic tote used to move goods."
    ],
    "hostelry": [
        "Travel history and older fiction — an inn or lodging house encountered on a journey.",
        "Hospitality history — older vocabulary for commercial lodging before “hotel” became the default term."
    ],
    "mound": [
        "Archaeology and landscape writing — an earthen rise that may mark a burial, settlement, or constructed site.",
        "Everyday description — a rounded pile of soil, stones, snow, or other material."
    ],
    "heap": [
        "Everyday narration — a pile of clothes, books, debris, or other loosely gathered objects.",
        "Informal speech — “a heap of trouble” or another large, unspecified amount."
    ],
    "pithiness": [
        "Editing and speechwriting — praising language that says a lot with very few words.",
        "Reviews and criticism — describing a concise line, slogan, or observation that lands forcefully."
    ],
    "ranginess": [
        "Sports and character description — a tall, long-limbed build with an extended reach.",
        "Landscape or design writing — something spread loosely across a broad area."
    ],
    "stultification": [
        "Policy or organizational criticism — rules that make a system ineffective or needlessly absurd.",
        "Education and cultural criticism — conditions that suppress thought, growth, or intellectual energy."
    ]
}

EXAMPLE_OVERRIDES = {
    "gendarme": "A pair of gendarmes directed traffic around the closed road outside the village.",
    "cask": "The distillery aged the whisky in an oak cask for twelve years.",
    "catatonia": "The psychiatrist evaluated the patient for catatonia after she became nearly immobile and stopped speaking.",
    "jaunty": "He tilted his hat at a jaunty angle and walked into the café.",
    "systolic": "Her blood pressure was 118 over 76, so the systolic reading was 118.",
    "skiffle": "The band began with skiffle songs played on guitar, washboard, and a homemade bass.",
    "mound": "The archaeologists mapped a low earthen mound beside the river.",
    "heap": "A heap of wet coats accumulated by the door.",
    "hammy": "The actor's hammy delivery made the serious scene unexpectedly funny.",
    "tote": "She used a canvas tote to carry groceries home.",
    "turnbuckle": "He tightened the turnbuckle until the cable was taut.",
    "verisimilitude": "The film's careful period details gave the story a strong sense of verisimilitude.",
    "gabardine": "The vintage shop displayed a navy gabardine trench coat.",
    "torpid": "After hours in the cold, the lizard was torpid and barely moved.",
    "umbra": "Observers inside the Moon's umbra experienced totality.",
    "millinery": "The costume department hired a millinery specialist to reproduce the elaborate hats.",
    "pyrrhic": "The campaign won the vote, but at such a cost that observers called it a Pyrrhic victory.",
    "rapport": "The interviewer quickly established rapport with the nervous witness.",
    "sump": "Heavy rain triggered the sump pump in the basement.",
    "waddle": "The ducklings waddled across the path in a tight group.",
    "allayed": "The engineer's inspection allayed concerns about the bridge.",
    "acmes": "The exhibition compared the artistic acmes of several dynasties.",
    "detente": "The agreement opened a period of détente between the rival governments.",
    "morass": "The project became trapped in a morass of overlapping permits and appeals.",
    "conniption": "He nearly had a conniption when he saw the repair estimate.",
    "whicker": "The mare gave a soft whicker when she saw the feed bucket.",
    "whispering": "They sat in the back row, whispering so quietly that no one else noticed.",
    "wimple": "The portrait shows a linen wimple wrapped around the woman’s head and neck.",
    "wristlock": "The instructor demonstrated a wristlock and then showed the safe escape.",
    "abase": "He refused to abase himself merely to win the official’s favor.",
    "abet": "The prosecutor argued that the accountant had helped abet the fraud.",
    "ablution": "Pilgrims washed at the fountain before performing the ritual ablution.",
    "abrogative": "The court considered whether the new clause had an abrogative effect.",
    "bountifully": "After a wet spring, the orchard yielded bountifully."
}


ETYMOLOGY_OVERRIDES = {
    "gendarme": "From French gendarme, shortened from gens d’armes, literally “people of arms.” The gens element is the same old “people/kind” family seen in words such as genteel and gentle.",
    "gabardine": "The fabric name is an early-1900s reshaping of gaberdine, an older word for a coarse outer garment. The older form travelled through Spanish and French and was associated with a traveller’s or pilgrim’s cloak.",
    "torpid": "From Latin torpidus, “numb” or “sluggish,” from torpere, “to be numb or inactive.” The same root appears in torpor.",
    "umbra": "Directly from Latin umbra, “shadow.” Penumbra adds Latin paene, “almost,” giving the useful pair umbra / penumbra.",
    "systolic": "From Greek systolē, “contraction” or “drawing together.” The same root gives systole, the contraction phase of the heartbeat.",
    "skiffle": "The musical sense developed in the 20th century from an older word associated with light, improvised entertainment. In Britain it became the name for folk/blues music played on simple or homemade instruments.",
    "verisimilitude": "From Latin veri similitudo, literally “likeness to truth”: verus means “true” and similitudo means “likeness.” Compare verity and similar.",
    "pyrrhic": "Named for King Pyrrhus of Epirus, whose costly victories against Rome inspired the phrase “Pyrrhic victory”: a success bought at ruinous cost.",
    "rapport": "Borrowed from French rapport, “relationship” or “connection,” from rapporter, “to bring back / relate.” It is in the same broad word-family as report.",
    "détente": "Borrowed from French détente, “relaxation” or “release of tension,” from détendre, “to loosen.” English uses it especially for easing political tension.",
    "detente": "Borrowed from French détente, “relaxation” or “release of tension,” from détendre, “to loosen.” English uses it especially for easing political tension.",
    "morass": "Borrowed through Dutch/French forms for marshy ground. The literal sense of a bog or swamp produced the figurative sense of a complicated situation that is hard to escape.",
    "conniption": "An American English word from the 19th century. Its deeper origin is uncertain, but it has long meant a fit of agitation, anger, or panic.",
    "pithiness": "Built from pithy + -ness. Pithy comes from pith, the dense core of a plant stem, which developed the figurative sense “the essential substance” of something.",
    "vicissitude": "From French vicissitude and Latin vicissitudo, “change” or “alternation.” The Latin root for change/turning is also visible in vice versa.",
    "vociferous": "From Latin vox, “voice,” + ferre, “to carry”: literally something like “voice-carrying.” The vox root is also behind vocal and voice.",
    "ward": "From Old English weard, “guarding, protection.” It belongs to the same old Germanic family as wary; guard is a parallel form that entered English through French.",
    "wastrel": "Built from waste + the disparaging suffix -rel in the 19th century: literally a person characterized by wasting.",
    "weighty": "Built from weight + -y. The literal idea of heaviness developed the figurative sense “important” or “serious,” as in a weighty argument.",
    "zaniness": "Built from zany + -ness. Zany ultimately comes from Italian Zanni, a stock comic servant in commedia dell’arte, which explains the sense of wild comic absurdity.",
    "allayed": "The base word allay came through Old French with the sense “to soften, lessen, or calm.” Its history is closely related in meaning to words such as alleviate.",
    "ambulated": "The base ambulate comes from Latin ambulare, “to walk about.” The same walking root appears in ambulatory and perambulate.",
    "acmes": "The singular acme comes from Greek akmē, “point, edge, highest point,” which naturally developed the sense “peak” or “culmination.”",
    "ax": "This is the common American spelling of axe. The word is ancient Germanic, going back through Old English æx; cognates occur across Germanic languages.",
    "soya": "Soya is a British variant of soy. English borrowed the word through Dutch soja from Japanese, ultimately connected with the East Asian word for soy sauce.",
    "turnbuckle": "A transparent English compound of turn + buckle: turning the central body draws the threaded ends inward or outward to change tension.",
    "millinery": "From milliner, originally a trader in fashionable goods associated with Milan. The word later narrowed to the making and selling of hats.",
    "hostelry": "From Middle English and Old French forms meaning an inn or lodging place; it is closely related to hostel and ultimately to the same hospitality word-family.",
    "catatonia": "Coined in 19th-century medical German from Greek roots meaning roughly “down/tight tension.” It entered international psychiatric vocabulary from German Katatonie.",
    "jaunty": "Related historically to genteel/gentle through French gentil. Its modern sense shifted toward a lively, stylish, self-confident manner.",
    "cask": "The modern barrel sense is old in English, though the deeper history is uncertain and has competing proposals. It is not etymologically just a shortened form of another modern English word.",
    "chamois": "Borrowed from French chamois, the name of the Alpine goat-antelope. The leather and cleaning-cloth senses come from the animal’s hide.",
    "tintype": "A 19th-century American compound of tin + type. Despite the name, the photographic plate was usually iron rather than tin.",
    "plebiscite": "From Latin plebis scitum, literally “decree of the common people”: plebs means “the common people.” Compare plebeian.",
    "philanthropy": "From Greek philanthrōpia, “love of humanity,” built from philos, “loving,” + anthrōpos, “human being.” Compare anthropological words such as anthropology.",
    "demurrer": "From Anglo-Norman / Old French demurrer, “to remain, delay.” In law it became the name for an objection that stops a case at the pleading stage.",
    "egregious": "From Latin egregius, literally “standing out from the flock” (ex, “out of,” + grex, “flock”). It once meant outstanding in a good sense before becoming strongly negative.",
    "quiddity": "From Medieval Latin quidditas, built on quid, “what?”: literally the “what-ness” or essential nature of a thing.",
    "ineffable": "From Latin ineffabilis, “unspeakable,” from in- “not” + effari “to speak out.” The same basic idea survives directly in its modern meaning.",
    "perspicacious": "From Latin perspicax, “sharp-sighted, discerning,” from perspicere, “to look through.” It is related to perspective and perspicuity.",
    "lugubrious": "From Latin lugubris, “mournful,” from lugere, “to mourn.” English has preserved the strongly gloomy sense.",
    "mendacity": "From Latin mendacitas, “falsehood,” built from mendax, “lying.” It belongs to the same Latin family as mendacious.",
    "aplomb": "Borrowed from French à plomb, literally “according to the plumb line.” Physical upright balance became the figurative sense of confident composure.",
    "bonhomie": "Borrowed from French bonhomie, from bon homme, literally “good man.” The phrase developed the sense of warm, easy good nature.",
    "canard": "Borrowed from French canard, literally “duck,” which also developed the French sense “hoax / false story.” English borrowed that figurative sense.",
    "prestidigitation": "From French prestidigitation, built from roots for “quick” and “finger.” The structure points directly to sleight-of-hand magic.",
    "somnambulistic": "Built on somnambulism, from Latin somnus, “sleep,” + ambulare, “to walk.” Compare ambulate: both contain the Latin walking root.",
    "intrauterine": "Built from intra-, “within,” + uterine, “of the uterus.” The structure literally means “within the uterus.”",
    "oxyacetylene": "A transparent chemical compound of oxy- (oxygen) + acetylene, naming a fuel-gas mixture of oxygen and acetylene.",
    "misogamist": "Built from Greek misos, “hatred,” + gamos, “marriage,” + -ist: literally a person opposed to marriage. Compare monogamy and polygamy for the gamos root.",
    "primogenitary": "Built on primogeniture, from Latin primus, “first,” + genitura, “birth.” The root structure points to inheritance by the firstborn.",
    "perambulation": "From Latin perambulare, “to walk through,” from per-, “through,” + ambulare, “to walk.” Compare ambulate and ambulatory.",
    "genuflect": "From Medieval Latin genuflectere, “to bend the knee,” from genu, “knee,” + flectere, “to bend.” Compare flex / inflection for the bending root.",
    "circumstantial": "From Latin circumstantia, “surrounding condition,” from circum, “around,” + stare, “to stand.”",
}

ETYMOLOGY_OVERRIDES.update({
    "ammonic": "Here Ammonic refers to cornu Ammonis, Latin for “horn of Ammon,” an old anatomical name for the hippocampal formation. The name evokes the curved ram’s horns associated with the god Ammon.",
    "amorist": "Built from Latin amor, “love,” + -ist: a person associated with love or writing about love. Compare amorous.",
    "anachronously": "Built on anachronism / anachronous. The Greek roots are ana- + chronos, “time”; chronology contains the same chronos root.",
    "apotheoses": "The singular apotheosis comes from Greek apotheōsis, “deification,” built on theos, “god.” Compare theology for the same theos root.",
    "bayed": "The base verb bay is an old hunting word for the barking or howling of hounds and came into English through French; bayed is its regular past form.",
    "boric": "Part of the boron / borax word-family. Borax came into European languages through Arabic and Persian; -ic forms the chemical adjective.",
    "castigation": "From Latin castigatio, “correction, reproof,” from castigare, “to correct or punish.” The same Latin verb gives castigate.",
    "consubstantiation": "Built from Latin con-, “together,” + substantia, “substance,” + -ation: literally coexistence in substance. Compare substance.",
    "cringle": "A nautical word probably from Dutch or Low German words for a ring or circle; its physical meaning is still a small ring or loop in sail rigging.",
    "crosstie": "A transparent compound of cross + tie: a member laid across the rails that ties them together at a fixed spacing.",
    "decantate": "Built on decant, the word for carefully pouring liquid away from sediment. Compare decanter, the vessel named from the same verb.",
    "delineation": "From Latin delineare, “to sketch with lines,” built on linea, “line.” The line connection is still visible in delineate.",
    "dextral": "From Latin dexter, “right-hand / on the right.” Compare dexterous, which developed from the positive associations of right-handed skill.",
    "dietarian": "Built from diet + -arian. Diet came through Greek and Latin words for a way of life or regimen; compare dietary.",
    "disapprobative": "Built from dis- + the approbation / approve family. Latin approbare meant “to approve”; dis- reverses the evaluation.",
    "disposure": "Built on dispose, from Latin disponere, “to arrange or place apart.” The same ponere, “to place,” root appears in position.",
    "excursive": "From the Latin excurs- family, from excurrere, “to run out.” Compare excursion: both carry the idea of ranging away from a main course.",
    "execratory": "Built on execrate, from Latin exsecrari, “to curse.” Compare execrable, something deserving strong condemnation.",
    "extrusive": "Built on extrude, from Latin extrudere, “to thrust out.” Compare extrusion, especially in geology and manufacturing.",
    "federacy": "From the federal / federation family, ultimately Latin foedus, “treaty, compact.” The root idea is people or states joined by agreement.",
    "fussbudgety": "A modern adjective built from fussbudget + -y. Fussbudget is an American colloquial word for a person who fusses excessively over small things.",
    "lancelet": "Built from lance + the diminutive -let, referring to the animal’s small, narrow, pointed shape.",
    "pronator": "From the pronation family, ultimately Latin pronus, “bent forward / face downward.” A pronator is therefore a muscle that turns toward the prone orientation.",
    "redolence": "From Latin redolere, “to give off a smell.” Compare redolent, which can mean fragrant or strongly suggestive of something.",
    "retrogressive": "Built on retrogress, ultimately Latin retrogradi, “to go backward.” Compare retrograde: both preserve the idea of backward movement.",
    "scruffiest": "The superlative of scruffy, a 19th-century adjective for something shabby or unkempt; the word is probably connected with scruff.",
    "shoofly": "A transparent compound of shoo + fly, originally naming things intended to drive flies away; later it was applied to several specific objects and foods.",
    "stultification": "Built on stultify, from Latin stultus, “foolish.” The history explains the sense of making something foolish, ineffective, or intellectually dull.",
    "suspensor": "From the suspend / suspension family, ultimately Latin suspendere, “to hang up.” The original physical idea is something that supports by suspension.",
    "swivet": "An American slang word of uncertain origin, recorded for a flustered, agitated, or exasperated state. Its deeper source is not securely known.",
    "whicker": "Probably imitative of a horse’s soft breathy call; it belongs semantically with neigh and whinny, though its deeper historical origin is uncertain."
})

ENCOUNTER_OVERRIDES = {
    "gendarme": [
        {"place":"French news report or police procedural","phrase":"“a gendarme waved the cars through”"},
        {"place":"Travel writing about rural France","phrase":"“the local gendarmes arrived first”"}
    ],
    "gabardine": [
        {"place":"Vintage clothing listing","phrase":"“a navy gabardine trench coat”"},
        {"place":"Costume-museum label","phrase":"“tailored in wool gabardine”"}
    ],
    "torpid": [
        {"place":"Field guide or nature documentary","phrase":"“the cold lizard remained torpid”"},
        {"place":"Political or institutional commentary","phrase":"“a torpid response to the crisis”"}
    ],
    "umbra": [
        {"place":"Eclipse map or astronomy article","phrase":"“inside the Moon’s umbra”"},
        {"place":"Optics textbook diagram","phrase":"“the central umbra and outer penumbra”"}
    ],
    "systolic": [
        {"place":"Blood-pressure reading at a clinic","phrase":"“a systolic pressure of 118 mmHg”"},
        {"place":"Cardiology or physiology textbook","phrase":"“during systolic contraction”"}
    ],
    "skiffle": [
        {"place":"British music-history documentary","phrase":"“the 1950s skiffle boom”"},
        {"place":"Record review or museum exhibit","phrase":"“a skiffle band with washboard and guitar”"}
    ],
    "verisimilitude": [
        {"place":"Film or book review","phrase":"“the period detail adds verisimilitude”"},
        {"place":"Historical-game criticism","phrase":"“verisimilitude without strict realism”"}
    ],
    "pyrrhic": [
        {"place":"War or political analysis","phrase":"“a Pyrrhic victory at enormous cost”"},
        {"place":"Sports column","phrase":"“a Pyrrhic win that exhausted the roster”"}
    ],
    "rapport": [
        {"place":"Therapy, interviewing, or teaching notes","phrase":"“build rapport before asking difficult questions”"},
        {"place":"Workplace profile","phrase":"“she had an easy rapport with the team”"}
    ],
    "morass": [
        {"place":"Business or policy commentary","phrase":"“a morass of permits and appeals”"},
        {"place":"Nature writing","phrase":"“the trail ended in a muddy morass”"}
    ],
    "conniption": [
        {"place":"Informal American conversation","phrase":"“he had a conniption over the bill”"},
        {"place":"Comic fiction","phrase":"“she nearly had a conniption”"}
    ],
    "turnbuckle": [
        {"place":"Rigging or fencing hardware instructions","phrase":"“tighten the turnbuckle until the cable is taut”"},
        {"place":"Sailing manual","phrase":"“adjust the stay with the turnbuckle”"}
    ],
    "millinery": [
        {"place":"Costume department or fashion museum","phrase":"“the production hired a millinery specialist”"},
        {"place":"Vintage department-store history","phrase":"“the millinery department was upstairs”"}
    ],
    "plebiscite": [
        {"place":"Constitutional-history article","phrase":"“the territory held a plebiscite on sovereignty”"},
        {"place":"International news explainer","phrase":"“a nationwide plebiscite on the proposal”"}
    ],
    "catatonia": [
        {"place":"Psychiatry note or hospital handoff","phrase":"“the team evaluated her for catatonia”"},
        {"place":"Medical news article","phrase":"“catatonia can include mutism and immobility”"}
    ],
    "jaunty": [
        {"place":"Fashion review","phrase":"“a jaunty hat tilted to one side”"},
        {"place":"Character description in a novel","phrase":"“he walked in with a jaunty step”"}
    ],
    "cask": [
        {"place":"Whisky label or distillery tour","phrase":"“matured for twelve years in an oak cask”"},
        {"place":"Beer review","phrase":"“a traditional cask ale”"}
    ],
    "hostelry": [
        {"place":"Historical travel writing","phrase":"“a roadside hostelry for weary travelers”"},
        {"place":"Older novel or local-history book","phrase":"“the village’s last surviving hostelry”"}
    ],
    "tintype": [
        {"place":"Photography museum label","phrase":"“an 1860s tintype portrait”"},
        {"place":"Antiques listing","phrase":"“a small tintype in a leather case”"}
    ],
    "demurrer": [
        {"place":"Civil-procedure textbook or court filing","phrase":"“the defendant filed a demurrer”"},
        {"place":"Legal news report","phrase":"“the judge overruled the demurrer”"}
    ],
    "pithiness": [
        {"place":"Editor’s margin note","phrase":"“keep the pithiness of the opening line”"},
        {"place":"Speech or book review","phrase":"“the slogan’s pithiness made it memorable”"}
    ],
    "vicissitude": [
        {"place":"Literary essay or biography","phrase":"“the vicissitudes of a long career”"},
        {"place":"Historical writing","phrase":"“through every vicissitude of the war”"}
    ],
    "vociferous": [
        {"place":"News report on a public meeting","phrase":"“vociferous opposition from residents”"},
        {"place":"Book or theater review","phrase":"“a vociferous crowd in the final scene”"}
    ],
    "waddle": [
        {"place":"Zoo sign or nature story","phrase":"“the penguins waddle toward the water”"},
        {"place":"Humorous character description","phrase":"“he waddled across the room”"}
    ],
    "ward": [
        {"place":"Hospital sign or chart","phrase":"“admitted to the surgical ward”"},
        {"place":"Court or guardianship document","phrase":"“a ward of the state”"}
    ],
    "weighty": [
        {"place":"Editorial or book review","phrase":"“a weighty argument about responsibility”"},
        {"place":"Formal speech","phrase":"“a weighty decision with lasting consequences”"}
    ],
    "zaniness": [
        {"place":"Comedy review","phrase":"“the show’s cheerful zaniness”"},
        {"place":"Animation or game criticism","phrase":"“lean into the visual zaniness”"}
    ],
    "whicker": [
        {"place":"Horse-training book or stable conversation","phrase":"“the mare gave a soft whicker”"},
        {"place":"Novel set around horses","phrase":"“a quiet whicker from the stall”"}
    ],
    "whispering": [
        {"place":"Dialogue in a novel or screenplay","phrase":"“they were whispering in the back row”"},
        {"place":"Voice / audio description","phrase":"“a whispering voice just above silence”"}
    ],
    "wimple": [
        {"place":"Medieval-art museum label","phrase":"“a linen wimple framing her face”"},
        {"place":"Historical costume guide","phrase":"“the nun’s white wimple”"}
    ],
    "wristlock": [
        {"place":"Judo / grappling instruction","phrase":"“finish the hold with a wristlock”"},
        {"place":"Combat-sports commentary","phrase":"“he escaped the wristlock”"}
    ],
    "abase": [
        {"place":"Literary novel or historical biography","phrase":"“refused to abase himself before the court”"},
        {"place":"Essay about status or humiliation","phrase":"“designed to abase a political rival”"}
    ],
    "abet": [
        {"place":"Criminal-law article or indictment","phrase":"“accused of aiding and abetting the scheme”"},
        {"place":"News report on wrongdoing","phrase":"“did nothing to abet the fraud”"}
    ],
    "ablution": [
        {"place":"Religion / ritual studies textbook","phrase":"“perform the morning ablutions”"},
        {"place":"Historical travel writing","phrase":"“a basin for ritual ablution”"}
    ],
    "abrogative": [
        {"place":"Statutory or constitutional analysis","phrase":"“an abrogative clause repealing the old rule”"},
        {"place":"Legal commentary","phrase":"“the amendment has an abrogative effect”"}
    ],
    "bountifully": [
        {"place":"Food or gardening writing","phrase":"“the orchard yielded bountifully”"},
        {"place":"Literary prose","phrase":"“the table was bountifully supplied”"}
    ],
    "ammonic": [
        {"place":"Neuroanatomy textbook","phrase":"“the Ammonic fields of the hippocampus”"},
        {"place":"Histology or neuroscience paper","phrase":"“Ammonic neurons in the hippocampal formation”"}
    ],
    "consubstantiation": [
        {"place":"Christian-theology textbook","phrase":"“the doctrine of consubstantiation”"},
        {"place":"Reformation-history essay","phrase":"“a debate over consubstantiation”"}
    ],
    "contraindicate": [
        {"place":"Drug label or prescribing information","phrase":"“kidney disease may contraindicate this treatment”"},
        {"place":"Clinical guideline","phrase":"“findings that contraindicate surgery”"}
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

@lru_cache(maxsize=2048)
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
    # Curated teaching definitions are independent semantic hints used to select
    # the matching dictionary sense, not to copy the source-test wording.
    hint=DEFINITION_OVERRIDES.get(word,"")
    if hint:
        ht=tokens(hint)
        overlap=len(gt & ht)
        score += 12*overlap
        if ht and overlap==0:
            score -= 18
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

def example_from(word, sense, entry):
    if word in EXAMPLE_OVERRIDES:
        return EXAMPLE_OVERRIDES[word], ""
    for ex in (sense.get("examples") or []):
        if isinstance(ex, str):
            t=clean(ex); ref=""
        else:
            t=clean(ex.get("text") or ex.get("example") or "")
            ref=clean(ex.get("ref") or "")
        if 18 <= len(t) <= 500 and not t.lower().startswith("for quotations using this term"):
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
    if not t:
        return ""
    if t.startswith("Etymology tree"):
        for marker in ("Borrowed from ", "Inherited from ", "Learned borrowing from ", "Ultimately from "):
            p=t.rfind(marker)
            if p>=0:
                return t[p:]
        p=t.rfind(" From ")
        if p>=0:
            return t[p+1:]
    return t

LANGUAGE_RE = re.compile(
    r"\b(Middle English|Old English|Late Middle English|Anglo-Norman|Middle French|Old French|French|Late Latin|Medieval Latin|New Latin|Latin|Ancient Greek|Greek|Old Norse|Old High German|Middle High German|German|Middle Dutch|Old Dutch|Dutch|Italian|Spanish|Portuguese|Arabic|Persian|Japanese|Sanskrit|Proto-West Germanic|Proto-Germanic|Proto-Indo-European)\s+([*A-Za-zÀ-žĀ-žÆæŒœØøÞþÐðʾʿ'’.-]+)(?:\s*\([“\"]([^”\"]{1,80})[”\"]\))?",
    re.I
)

def best_raw_etymology(entries, preferred):
    t=clean((preferred or {}).get("etymology_text") or "")
    if t:
        return t
    for e in entries or []:
        t=clean(e.get("etymology_text") or "")
        if t:
            return t
    return ""

def derivational_info(word, raw_ety, raw_gloss):
    lemma=form_reference(raw_gloss)
    if lemma:
        return lemma, ""
    t=clean(raw_ety)
    for lead in ("From ","Equivalent to "):
        if t.startswith(lead):
            rest=t[len(lead):]
            if " + -" in rest:
                base,tail=rest.split(" + -",1)
                base=clean(base)
                suffix="-"+re.split(r"[^A-Za-z-]",tail,1)[0]
                if re.fullmatch(r"[A-Za-z][A-Za-z'’-]*",base) and normalize_word(base)!=normalize_word(word):
                    return base,suffix
    return "", ""

def base_word_info(base):
    if not base:
        return "", ""
    entries,_=get_jsonl(base)
    if not entries:
        return "", ""
    entry,sense=pick_entry(entries,base,{"definitions":[],"neighbors":[]})
    gloss=sense_gloss(sense)
    raw=best_raw_etymology(entries,entry)
    return clean(gloss), clean(raw)

def concise_origin(raw, max_chars=320):
    t=clean_etymology_text(raw)
    if not t:
        return ""
    t=re.split(r"\b(?:Cognates?|Further reading|References?|Etymology note)\b",t,maxsplit=1,flags=re.I)[0].strip(" ;")
    matches=[]
    seen=set()
    for m in LANGUAGE_RE.finditer(t):
        lang=clean(m.group(1)); form=clean(m.group(2)); gloss=clean(m.group(3) or "")
        key=(lang.lower(),form.lower())
        if key not in seen:
            seen.add(key); matches.append((lang,form,gloss))
    if len(matches)>=2:
        first=matches[0]
        # Proto reconstructions are often visually noisy and less useful to a learner;
        # prefer the deepest attested classical/historical language in a short note.
        nonproto=[x for x in matches[1:] if not x[0].lower().startswith("proto-") and not x[1].startswith("*")]
        last=(nonproto[-1] if nonproto else matches[1])
        def fmt(x):
            lang,form,gloss=x
            f=f"{lang} {form}"
            if gloss: f+=f" (“{gloss}”)"
            return f
        return f"From {fmt(first)}, ultimately from {fmt(last)}."
    sent=re.split(r"(?<=[.!?])\s+",t)[0]
    if len(sent)<=max_chars:
        return sent
    cut=sent[:max_chars].rsplit(",",1)[0].rsplit(";",1)[0].strip()
    return (cut if len(cut)>80 else sent[:max_chars].rstrip())+"…"

def heuristic_base(word):
    w=word.lower()
    candidates=[]
    if w.endswith("ing") and len(w)>6:
        candidates += [w[:-3], w[:-3]+"e"]
    if w.endswith("ied") and len(w)>6:
        candidates += [w[:-3]+"y"]
    elif w.endswith("ed") and len(w)>5:
        candidates += [w[:-2], w[:-1]]
    if w.endswith("ness") and len(w)>7:
        stem=w[:-4]; candidates += [stem, stem[:-1]+"y" if stem.endswith("i") else stem]
    if w.endswith("ly") and len(w)>6:
        candidates += [w[:-2]]
    if w.endswith("s") and len(w)>5 and not w.endswith(("ss","us","is")):
        candidates += [w[:-1], w[:-2] if w.endswith("es") else ""]
    for c in candidates:
        if not c or normalize_word(c)==normalize_word(word): continue
        entries,_=get_jsonl(c)
        if entries:
            return c
    return ""

def origin_for_base(base, depth=0):
    if not base or depth>2:
        return ""
    base_gloss,base_raw=base_word_info(base)
    nested,suffix=derivational_info(base,base_raw,base_gloss)
    if not nested and (not base_raw or re.match(r"^(?:From|Equivalent to)\s+"+re.escape(base)+r"\s+\+\s+-",base_raw,re.I)):
        nested=heuristic_base(base)
        suffix=""
    if nested and normalize_word(nested)!=normalize_word(base):
        deeper=origin_for_base(nested,depth+1)
        stem=f"{base} is built from {nested}" + (f" + {suffix}" if suffix else "") + "."
        return f"{stem} {deeper}".strip()
    return concise_origin(base_raw)

def etymology_brief(word, entries, entry, raw_gloss):
    if word in ETYMOLOGY_OVERRIDES:
        return ETYMOLOGY_OVERRIDES[word]
    raw=best_raw_etymology(entries,entry)
    base,suffix=derivational_info(word,raw,raw_gloss)
    if not base and (not raw or re.match(r"^(?:From|Equivalent to)\s+\S+\s+\+\s+-",raw,re.I)):
        base=heuristic_base(word)
        suffix=""
    if base:
        base_gloss,_=base_word_info(base)
        gloss_part=""
        if base_gloss:
            bg=clean(base_gloss).rstrip(".")
            if len(bg)>88: bg=bg[:85].rsplit(" ",1)[0]+"…"
            gloss_part=f" (“{bg}”)"
        lead=(f"Built from {base}{gloss_part}" + (f" + {suffix}" if suffix else "") + ".")
        origin=origin_for_base(base)
        if origin and not re.match(r"^(?:From|Equivalent to)\s+"+re.escape(base)+r"\s+\+\s+-",origin,re.I):
            return (f"{lead} {origin}")[:520]
        return lead+" A deeper origin is not stated in the bundled source."
    brief=concise_origin(raw)
    if brief:
        return brief
    return "No reliable deeper origin is included in the bundled dictionary source."

def phrase_from_example(word, example):
    e=clean(example)
    if not e or e.startswith(("In context,", "The writer chose", "The description was", "In this vocabulary set")):
        return ""
    if any(ch in e for ch in ("ſ","þ","ð")):
        return ""
    m=re.search(r"\b"+re.escape(word)+r"\b",e,re.I)
    if not m:
        return ""
    before=e[:m.start()].split()
    after=e[m.end():].split()
    chunk=" ".join(before[-4:]+[e[m.start():m.end()]]+after[:5]).strip(" ,;:")
    chunk=re.sub(r"\s+([,.;:!?])",r"\1",chunk)
    if len(chunk)>92:
        chunk=chunk[:89].rsplit(" ",1)[0]+"…"
    return "“"+chunk.rstrip(".")+"”"

def indefinite(word):
    return "an" if word[:1].lower() in "aeiou" else "a"

def domain_has(text, keys):
    toks=set(re.findall(r"[a-z]+",clean(text).lower()))
    for k in keys:
        if k.endswith("*"):
            stem=k[:-1]
            if any(t.startswith(stem) for t in toks):
                return True
        elif k in toks:
            return True
    return False

def generic_phrase(word, pos, definition, index=0, place="", domain="general"):
    p=(pos or "").lower()
    d=clean(definition).lower()
    person=bool(re.search(r"^(?:a|an)\s+(?:person|man|woman|someone)|^one who",d))
    abstract=bool(re.match(r"^(?:the )?(?:act|state|quality|process|condition|practice|ability|degree)\b",d))
    if p in ("adj","adjective"):
        nouns={"fashion":"style","medical":"finding","biology":"trait","chemistry":"compound","legal":"provision","finance":"policy","language":"construction","music":"passage","food":"flavor","military":"description","religion":"doctrine","engineering":"component","personality":"remark"}
        return f"“{indefinite(word)} {word} {nouns.get(domain,'description')}”"
    if p in ("adv","adverb"):
        verbs={"medical":"presented","legal":"argued","music":"played","personality":"responded"}
        return f"“{verbs.get(domain,'responded')} {word}”"
    if p=="verb":
        if word.endswith("ed"):
            if any(k in d for k in ("calm","reliev","less intense","reduce")):
                return f"“their fears were {word}”"
            return f"“they had {word} it by then”"
        if word.endswith("ing"):
            return f"“kept {word} through the scene”"
        frames=[
            (("humiliat","degrad","lower"),"someone publicly"),
            (("crime","wrongdoing","assist","encourage"),"the scheme"),
            (("reject","renounce","disavow"),"the old belief"),
            (("walk","wander","move"),"across the room"),
            (("deceive","defraud","cheat"),"an unsuspecting buyer"),
            (("prevent","hinder","avert"),"a larger problem"),
            (("praise","extol"),"the achievement"),
            (("adorn","decorate"),"the hall"),
            (("drink","alcohol"),"after dinner"),
            (("block","obstruct"),"the opening"),
            (("pour","liquid"),"the wine carefully"),
        ]
        for keys,obj in frames:
            if any(k in d for k in keys):
                return f"“to {word} {obj}”"
        return f"“decided to {word}”"
    if person:
        return f"“{indefinite(word)} {word} in the account”"
    if domain=="medical":
        return f"“the {word} on the scan”" if any(k in d for k in ("bone","muscle","membrane","organ","structure")) else f"“{word} noted in the chart”"
    if domain=="biology":
        return f"“the {word} in the specimen”"
    if domain=="chemistry":
        return f"“the {word} in the sample”"
    if domain=="legal":
        return f"“the {word} in the filing”"
    if domain=="finance":
        return f"“the {word} in the policy”"
    if domain=="language":
        return f"“the {word} in the sentence”"
    if domain=="music":
        return f"“a {word} in the score”"
    if domain=="food":
        return f"“{word} on the menu”"
    if domain=="military":
        return f"“the {word} in the museum collection”"
    if domain=="religion":
        return f"“the {word} in the theology text”"
    if domain=="engineering":
        return f"“the {word} in the assembly”"
    if domain=="fashion":
        return f"“the {word} in the catalog”"
    if domain=="personality" or abstract:
        return f"“a striking display of {word}”"
    if word.endswith("s") and not word.endswith(("ss","us")):
        return f"“several {word} in the account”"
    return f"“{indefinite(word)} {word} in the passage”"

def encounter_cards(word, definition, pos, labels, example):
    if word in ENCOUNTER_OVERRIDES:
        return ENCOUNTER_OVERRIDES[word]
    d=clean(definition).lower()
    rare=any(x in (labels or []) for x in ("archaic","obsolete","rare","dated","historical","literary"))
    domains=[
        ("fashion",("fabric","cloth","garment","hat","tailor*","wool","cotton","dress","coat","shoe"),
         ["Vintage clothing listing","Costume-museum or fashion-history label"]),
        ("medical",("heart","blood","vein","lung","bone","muscle","organ","tissue","medical","disease","surgical","uterus","anatom*","psychiatr*"),
         ["Medical chart or clinic handout","Anatomy / physiology textbook"]),
        ("biology",("gene","chromosome","cell","protein","species","animal","bird","insect","fish","plant","biology","axon"),
         ["Biology textbook or lab handout","Field guide or science-museum label"]),
        ("chemistry",("chemical","compound","polymer","acid","carbon","oxide","mineral","molten"),
         ["Chemistry / materials-science lab manual","Technical datasheet or geology textbook"]),
        ("legal",("law","legal","court","crime","government","vote","treaty","policy","trustee"),
         ["Court filing or legal explainer","Newspaper public-affairs article"]),
        ("finance",("money","coin","fund","debt","business","market","insured","finance"),
         ["Insurance policy or financial statement","Business-news article"]),
        ("language",("language","speech","grammar","pronoun","syllable","vowel","consonant","linguist*"),
         ["Grammar / linguistics textbook","Editor’s margin note or literary analysis"]),
        ("music",("music","note","sung","instrument","song","melody"),
         ["Album review or concert program","Music-history textbook"]),
        ("food",("food","dish","meal","cook*","meat","sauce","drink","bread","stew","herb"),
         ["Restaurant menu or food review","Cookbook or culinary-history article"]),
        ("military",("weapon","ammunition","firearm","sword","military","soldier","battle","war"),
         ["Military-museum label","Historical nonfiction or reenactment guide"]),
        ("religion",("marriage","religious","church","priest","theolog*","angel","worship","divine"),
         ["Religion / theology textbook","Church-history or museum exhibit"]),
        ("engineering",("room","building","roof","architecture","railroad","track","cable","road","soil","construction"),
         ["Engineering / maintenance manual","Architecture or infrastructure description"]),
        ("personality",("emotion","mood","behavior","foolish","stubborn","cheerful","angry","calm","style","manner"),
         ["Character description in a novel","Book / film review"]),
    ]
    domain="general"; places=None
    for name,keys,p in domains:
        if domain_has(d,keys):
            domain=name; places=p; break
    if not places:
        person=bool(re.search(r"^(?:a|an)\s+(?:person|man|woman|someone)|^one who",d))
        abstract=bool(re.match(r"^(?:the )?(?:act|state|quality|process|condition|practice|ability|degree)\b",d))
        if rare:
            places=["Historical novel or archival document","Literary commentary on older language"]
        elif person:
            places=["Biography, profile, or character sketch","Novel or historical account"]
        elif abstract:
            places=["Essay, review, or long-form article","Academic or cultural criticism"]
        elif (pos or "").lower() in ("adj","adjective","adv","adverb"):
            places=["Book / film review","Character description in fiction"]
        elif (pos or "").lower()=="verb":
            places=["Long-form news feature","Novel or memoir"]
        else:
            places=["Magazine feature or reference entry","Textbook, catalog, or museum label"]
    ex=phrase_from_example(word,example)
    p1=generic_phrase(word,pos,definition,0,places[0],domain)
    p2=ex or generic_phrase(word,pos,definition,1,places[1],domain)
    if p2==p1:
        p2=generic_phrase(word,pos,definition,1,places[1],domain)
    return [{"place":places[0],"phrase":p1},{"place":places[1],"phrase":p2}]

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
        if any(re.search(r"\\b"+re.escape(k)+r"\\w*\\b", d) for k in keys):
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
    raw_ety=best_raw_etymology(entries,entry)
    ety=clean_etymology_text(raw_ety)
    ety_brief=etymology_brief(word,entries,entry,raw_gloss)
    ex,exref=example_from(word,sense,entry)
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
        "linkedLemma":form_reference(raw_gloss),
        "sourceDefinition":source_definition,
        "partOfSpeech":pos,
        "etymology":ety,
        "etymologyBrief":ety_brief,
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
        "encounters":encounter_cards(word,definition,pos,labels,ex),
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
                print(f"FAILED {w}: {type(e).__name__}: {e}")
                failures.append(w)
                src=SOURCE.get(w,{})
                data[w]={
                    "word":w,"definition":(src.get("definitions") or [""])[0],
                    "quizDefinition":(src.get("definitions") or [""])[0],
                    "rawDictionaryDefinition":"","linkedLemma":"",
                    "sourceDefinition":(src.get("definitions") or [""])[0],
                    "partOfSpeech":"","etymology":"",
                    "etymologyBrief":"No reliable deeper origin is included in the bundled dictionary source.",
                    "example":fallback_example(w,(src.get("definitions") or [""])[0],""),
                    "exampleCitation":"","ipa":[],"audio":"","synonyms":[],"related":[],
                    "usageLabels":[],"sourceNeighbors":src.get("neighbors",[]),
                    "courseSynonyms":src.get("neighbors",[]),
                    "courseCue":(src.get("definitions") or [""])[0],
                    "modernUses":modern_uses(w,(src.get("definitions") or [""])[0],"",[]),
                    "encounters":encounter_cards(w,(src.get("definitions") or [""])[0],"",[],fallback_example(w,(src.get("definitions") or [""])[0],"")),
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
      "etymology_briefs":sum(1 for x in ordered.values() if x.get("etymologyBrief")),
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
