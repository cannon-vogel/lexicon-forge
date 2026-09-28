'use strict';
let QUESTIONS=[];
let ALL_WORDS=[];
let WORD_META={};
let CORE_WORDS=[];
let SOURCE_INFO={};
let STATIC_WORD_DATA={};

const KEY='lexiconForge.v1';
const DAY=86400000;
const INTERVALS=[0,5*60*1000,20*60*1000,DAY,3*DAY,7*DAY,14*DAY,30*DAY,90*DAY];
const FULL_XP_MILESTONE=88794;
const PIGEONS=[
  {id:'crumb',name:'Crumb Scout',price:75,rarity:'TINY',style:1,desc:'A practical sidewalk pigeon with three emergency crumbs.'},
  {id:'scarf',name:'Scarf Pigeon',price:225,rarity:'COZY',style:2,desc:'Soft scarf. Excellent posture. Knows where the warm vents are.'},
  {id:'rain',name:'Drizzle Bird',price:650,rarity:'DAPPER',style:3,desc:'Tiny yellow raincoat for extremely serious puddle inspection.'},
  {id:'prof',name:'Professor Pigeon',price:1600,rarity:'SCHOLAR',style:4,desc:'Mortarboard, spectacles, and strong opinions about seminar formatting.'},
  {id:'disco',name:'Disco Pigeon',price:4200,rarity:'FANCY',style:5,desc:'Star glasses and maximum dance-floor confidence.'},
  {id:'royal',name:'Pigeon Royal',price:9500,rarity:'REGAL',style:6,desc:'A velvet cape and crown for a bird with absolutely no constitutional limits.'},
  {id:'cosmic',name:'Cosmic Grandpigeon',price:FULL_XP_MILESTONE,requiresFull:true,rarity:'MYTHIC',style:7,desc:'The final bird: jeweled crown, nebula plumage, and the full-course XP requirement.'}
];
const ENRICH_TTL=30*DAY;
let state=null;
let session=null;
let lesson=null;
let wordPage=30;
let wordRandom=null;

function parseCSV(text){
  const rows=[]; let row=[],field='',quoted=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(quoted){
      if(c==='"'&&text[i+1]==='"'){field+='"';i++;}
      else if(c==='"')quoted=false;
      else field+=c;
    }else{
      if(c==='"')quoted=true;
      else if(c===','){row.push(field);field='';}
      else if(c==='\n'){row.push(field);rows.push(row);row=[];field='';}
      else if(c!=='\r')field+=c;
    }
  }
  if(field.length||row.length){row.push(field);rows.push(row);}
  return rows;
}

async function loadData(){
  const [qText,tText,wordData]=await Promise.all([
    fetch('questions.csv').then(r=>{if(!r.ok)throw new Error('questions.csv');return r.text()}),
    fetch('terms.csv').then(r=>{if(!r.ok)throw new Error('terms.csv');return r.text()}),
    fetch('word_data.json').then(r=>{if(!r.ok)throw new Error('word_data.json');return r.json()})
  ]);
  STATIC_WORD_DATA=wordData.words||{};
  const qr=parseCSV(qText), qh=qr.shift(), qi=Object.fromEntries(qh.map((h,i)=>[h,i]));
  QUESTIONS=qr.filter(r=>r.length>1).map(r=>({
    id:'q'+r[qi.question_number],n:Number(r[qi.question_number]),prompt:r[qi.prompt],block:r[qi.block],pick:Number(r[qi.pick]),
    options:[1,2,3,4,5].map(n=>r[qi['option_'+n]]),correct:r[qi.correct_indices].split(';').filter(Boolean).map(Number)
  }));
  const tr=parseCSV(tText), th=tr.shift(), ti=Object.fromEntries(th.map((h,i)=>[h,i]));
  for(const r of tr.filter(r=>r.length>1)){
    const term=r[ti.term]; if(!term)continue; ALL_WORDS.push(term);
    WORD_META[term]={occurrences:Number(r[ti.occurrences]||1),source:r[ti.source]||'',questionNumbers:String(r[ti.question_numbers]||'').split(';').map(x=>Number(x.trim())).filter(Boolean)};
  }
  ALL_WORDS.sort((a,b)=>a.localeCompare(b));
  buildSourceInfo();
}

function buildSourceInfo(){
  const ordered=[];
  for(const q of QUESTIONS){
    const correct=correctWords(q);
    const quoted=(q.prompt.match(/[“"]([^”"]+)[”"]/)||[])[1]||'';
    const localDef=q.block==='def'?quoted:'';
    for(const w of correct){
      if(!SOURCE_INFO[w])SOURCE_INFO[w]={definitions:[],relations:[],questions:[],neighbors:[]};
      if(localDef)SOURCE_INFO[w].definitions.push(localDef);
      SOURCE_INFO[w].questions.push(q.n);
      const peers=correct.filter(x=>x!==w);
      if(peers.length){SOURCE_INFO[w].neighbors.push(...peers);SOURCE_INFO[w].relations.push('Closely related in the source set: '+peers.join(', ')+'.');}
      if(!ordered.includes(w))ordered.push(w);
    }
    if(q.block==='1of5'&&quoted){
      const w=quoted;
      if(!SOURCE_INFO[w])SOURCE_INFO[w]={definitions:[],relations:[],questions:[],neighbors:[]};
      SOURCE_INFO[w].questions.push(q.n);
      SOURCE_INFO[w].neighbors.push(...correct);
      SOURCE_INFO[w].relations.push('Synonym target in the source set: '+correct.join(', ')+'.');
      if(!ordered.includes(w))ordered.push(w);
    }
  }
  for(const [w,info] of Object.entries(SOURCE_INFO)){
    info.questions=[...new Set(info.questions)];
    info.neighbors=[...new Set(info.neighbors.filter(x=>x!==w))];
    info.definitions=[...new Set(info.definitions)];
    info.relations=[...new Set(info.relations)];
  }
  CORE_WORDS=ordered;
}

function freshState(){return {version:1,xp:0,xpSpent:0,pigeons:{},core:{},full:{},dict:{},enrich:{},learn:{},history:[],settings:{sessionSize:12}}}
function loadState(){
  try{
    const x=JSON.parse(localStorage.getItem(KEY));
    if(!x||x.version!==1)return freshState();
    const s=freshState();
    Object.assign(s,x);
    s.settings=Object.assign({sessionSize:12},x.settings||{});
    s.core=x.core||{};s.full=x.full||{};s.dict=x.dict||{};s.enrich=x.enrich||{};s.learn=x.learn||{};s.history=x.history||[];s.xpSpent=Number(x.xpSpent||0);s.pigeons=x.pigeons||{};
    for(const [w,d] of Object.entries(s.dict))if(d?.error)delete s.dict[w];
    return s;
  }catch{return freshState()}
}
function save(update=true){localStorage.setItem(KEY,JSON.stringify(state));if(update)updateDashboard()}
function prog(deck,id){const root=deck==='core'?state.core:state.full;return root[id]||(root[id]={stage:0,due:0,attempts:0,correct:0,lapses:0,last:0})}
function shuffle(a){a=[...a];for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
function normalize(s){return String(s||'').toLowerCase().trim().replace(/[’']/g,"'").replace(/[^a-z0-9' -]+/g,'').replace(/\s+/g,' ')}
function setEq(a,b){a=[...a].map(normalize).sort();b=[...b].map(normalize).sort();return a.length===b.length&&a.every((x,i)=>x===b[i])}
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>t.classList.remove('show'),2800)}
function availableXP(){return Math.max(0,Math.floor((state?.xp||0)-(state?.xpSpent||0)))}
function level(){return Math.floor(Math.sqrt(state.xp/80))+1}
function stageName(s){return ['new','fresh','learning','1 day','3 days','1 week','2 weeks','1 month','3 months'][Math.min(s,8)]}
function fmtDue(ts){if(!ts||ts<=Date.now())return 'due';const d=ts-Date.now();if(d<3600000)return Math.ceil(d/60000)+'m';if(d<DAY)return Math.ceil(d/3600000)+'h';return Math.ceil(d/DAY)+'d'}
function recentAccuracy(){const h=state.history.slice(-60);if(!h.length)return null;return Math.round(100*h.filter(x=>x.correct).length/h.length)}
function countDue(root){const now=Date.now();return Object.values(root).filter(p=>p.attempts&&p.due<=now).length}
function countMastered(root){return Object.values(root).filter(p=>p.stage>=5).length}
function introducedCount(){return Object.values(state.learn||{}).filter(x=>x?.introduced).length}
function updateDashboard(){
  const cm=countMastered(state.core),due=countDue(state.core)+countDue(state.full),acc=recentAccuracy();
  document.getElementById('levelTop').textContent=level();document.getElementById('xpTop').textContent=availableXP();document.getElementById('dueTop').textContent=due;
  document.getElementById('learnedCount').textContent=introducedCount();document.getElementById('coreMastered').textContent=cm;document.getElementById('reviewDue').textContent=due;document.getElementById('retention').textContent=acc===null?'—':acc+'%';
  document.getElementById('coreBar').style.width=(100*cm/Math.max(1,QUESTIONS.length))+'%';
  document.getElementById('sessionSize').value=state.settings.sessionSize||12;
  renderHabitat();
  if(document.getElementById('pigeonShop'))renderPigeonShop();
}

function switchView(id){
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===id));
  document.querySelectorAll('.navbtn').forEach(b=>b.classList.toggle('active',b.dataset.view===id));
  if(id==='words')renderWords();if(id==='pigeons')renderPigeonShop();window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('.navbtn').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));

function dueSorted(ids,deck){const root=deck==='core'?state.core:state.full,now=Date.now();return ids.filter(id=>root[id]?.attempts&&root[id].due<=now).sort((a,b)=>root[a].due-root[b].due)}
function learnedUnpracticed(){return Object.keys(state.learn||{}).filter(w=>state.learn[w]?.introduced&&!state.full[w]?.attempts&&ALL_WORDS.includes(w))}
function chooseCore(n){const ids=QUESTIONS.map(q=>q.id),root=state.core;let out=dueSorted(ids,'core');const seenFuture=ids.filter(id=>root[id]?.attempts&&root[id].due>Date.now()).sort((a,b)=>root[a].due-root[b].due);const fresh=ids.filter(id=>!root[id]?.attempts);return [...new Set([...out,...fresh,...seenFuture])].slice(0,n)}
function chooseLearnedFull(n){const due=dueSorted(ALL_WORDS,'full');const fresh=learnedUnpracticed();const future=ALL_WORDS.filter(id=>state.full[id]?.attempts&&state.full[id].due>Date.now()).sort((a,b)=>state.full[a].due-state.full[b].due);return [...new Set([...due,...fresh,...future])].slice(0,n)}
function chooseReview(n){
  const q=[];
  for(const id of dueSorted(ALL_WORDS,'full'))q.push({deck:'full',id});
  for(const id of learnedUnpracticed())if(!q.some(x=>x.id===id))q.push({deck:'full',id});
  for(const id of dueSorted(QUESTIONS.map(q=>q.id),'core'))q.push({deck:'core',id});
  return q.slice(0,n);
}
function startSession(deck,customWords=null){
  const n=Number(state.settings.sessionSize)||12;let queue=[];
  if(customWords)queue=customWords.map(id=>({deck:'full',id}));
  else if(deck==='core')queue=chooseCore(n).map(id=>({deck:'core',id}));
  else if(deck==='full')queue=chooseLearnedFull(n).map(id=>({deck:'full',id}));
  else queue=chooseReview(n);
  if(!queue.length){toast('Learn a few words first, then come back to review.');switchView('learn');return}
  session={queue,index:0,answered:0,correct:0,retries:{},assisted:false,locked:false};switchView('game');renderCard();
}

document.getElementById('dailyBtn').onclick=()=>startSession('review');
document.getElementById('coreBtn').onclick=()=>startSession('core');
document.getElementById('quitBtn').onclick=()=>{session=null;switchView('home')};

// ---------- Learning mode ----------
function learningPool(scope){return scope==='all'?ALL_WORDS:CORE_WORDS}
function chooseLessonWords(scope,n){
  const pool=learningPool(scope);
  const unseen=pool.filter(w=>!state.learn[w]?.introduced);
  const seen=pool.filter(w=>state.learn[w]?.introduced).sort((a,b)=>(state.learn[a]?.lastSeen||0)-(state.learn[b]?.lastSeen||0));
  return [...unseen,...seen].slice(0,n);
}
function startLesson(){
  const scope=document.getElementById('learnScope').value||'core',n=Number(document.getElementById('learnSize').value)||6,words=chooseLessonWords(scope,n);
  if(!words.length){toast('Everything in this pool has been introduced.');return}
  lesson={scope,words,index:0,stories:{},checked:{}};
  document.getElementById('learnEmpty').classList.add('hidden');document.getElementById('learnStage').classList.remove('hidden');switchView('learn');renderLessonWord();
}
document.getElementById('learnBtn').onclick=()=>{switchView('learn');setTimeout(startLesson,80)};
document.getElementById('startLearnBtn').onclick=startLesson;document.getElementById('startLearnBtn2').onclick=startLesson;
document.getElementById('endLearnBtn').onclick=()=>{lesson=null;document.getElementById('learnStage').classList.add('hidden');document.getElementById('learnEmpty').classList.remove('hidden')};

function localStory(word){
  const src=SOURCE_INFO[word]||{};
  const definition=src.definitions?.[0]||'';
  const relation=src.relations?.[0]||'';
  const neighbors=src.neighbors||[];
  const meta=WORD_META[word]||{};
  let sourceCue='';
  if(definition)sourceCue='Course cue: “'+definition+'”';
  else if(neighbors.length)sourceCue='Course synonym/group: '+neighbors.join(', ')+'.';
  else if(relation)sourceCue=relation;
  else if(meta.questionNumbers?.length)sourceCue='This word appears in source question '+meta.questionNumbers.join(', ')+'.';
  return {word,definition,relation,neighbors,sourceCue,questions:src.questions||meta.questionNumbers||[]};
}

function renderLessonWord(){
  if(!lesson)return;
  if(lesson.index>=lesson.words.length)return finishLesson();
  const word=lesson.words[lesson.index],local=localStory(word),story=staticWordStory(word),card=document.getElementById('learnCard');
  lesson.stories[word]=story;
  document.getElementById('learnCount').textContent=(lesson.index+1)+' / '+lesson.words.length;
  document.getElementById('learnBar').style.width=(100*lesson.index/lesson.words.length)+'%';
  card.innerHTML='';

  const top=el('div',{class:'storytop'}),wh=el('div',{class:'wordhero'});
  const pron=[story.partOfSpeech,(story.ipa||[])[0]].filter(Boolean).join(' · ');
  wh.append(
    el('div',{class:'eyebrow'},'WORD '+(lesson.index+1)),
    el('h2',{},word),
    el('div',{class:'phonetic'},pron||'Tap “Hear it” for pronunciation')
  );
  const speak=el('button',{class:'btn secondary mini'},'Hear it');
  speak.onclick=()=>playWordAudio(word,story);
  top.append(wh,speak);card.append(top);

  const grid=el('div',{class:'storygrid'});
  const meaning=story.definition||local.definition||local.relation||'Meaning unavailable.';
  grid.append(storyPanel('Meaning','storyMeaning',meaning));

  const history=story.etymologyBrief||story.etymology||'No etymology was available in the bundled lexical record.';
  const hp=storyPanel('Word history','storyEtymology',history);
  if(story.entryAvailable)hp.append(sourceLink('https://en.wiktionary.org/wiki/'+encodeURIComponent(word),'Wiktionary-derived data'));
  grid.append(hp);

  const exampleText=story.example||'No example sentence was available for this entry.';
  const context=storyPanel('In the wild','storyExample',exampleText);
  context.classList.add('full');
  if(story.example)context.querySelector('p').classList.add('quote');
  if(story.exampleCitation)context.append(el('div',{class:'sourcefoot'},story.exampleCitation));
  grid.append(context);

  const modern=el('div',{class:'storypanel full encounter-panel'});
  modern.append(el('h4',{},'Where you might actually encounter it'));
  const uses=el('div',{class:'encounter-grid'});
  const encounters=(story.encounters||[]).length?story.encounters:[
    {place:'Feature article or nonfiction book',phrase:'“'+word+'” in context'},
    {place:'Specialist textbook / museum label',phrase:'“'+word+'”'}
  ];
  for(const e of encounters.slice(0,2)){
    const item=el('div',{class:'encounter'});
    item.append(
      el('div',{class:'encounter-label'},e.place||'In context'),
      el('div',{class:'encounter-phrase'},e.phrase||('“'+word+'”'))
    );
    uses.append(item);
  }
  modern.append(uses);grid.append(modern);

  const connect=el('div',{class:'storypanel full'});
  connect.append(el('h4',{},'Connections'));
  const courseSyns=[...new Set([...(story.courseSynonyms||[]),...(story.sourceNeighbors||[])].filter(x=>normalize(x)!==normalize(word)))];
  if(story.courseCue)connect.append(el('p',{class:'course-line'},'Course cue: “'+story.courseCue+'”'));
  if(courseSyns.length){
    connect.append(el('div',{class:'connection-label'},courseSyns.length===1?'Course synonym':'Course synonyms / group'));
    const cc=el('div',{class:'connection-list'});
    for(const n of courseSyns)cc.append(el('span',{class:'connection'},n));
    connect.append(cc);
  }
  const dictRelated=[...new Set([...(story.synonyms||[]),...(story.related||[])].filter(x=>normalize(x)!==normalize(word)&&!courseSyns.includes(x)))].slice(0,8);
  if(dictRelated.length){
    connect.append(el('div',{class:'connection-label'},'Dictionary neighbors'));
    const dc=el('div',{class:'connection-list'});
    for(const n of dictRelated)dc.append(el('span',{class:'connection'},n));
    connect.append(dc);
  }
  if((story.usageLabels||[]).length)connect.append(el('p',{class:'micro',style:'margin-top:10px'},'Usage: '+story.usageLabels.join(' · ')));
  if(!story.courseCue&&!courseSyns.length&&!dictRelated.length)connect.append(el('p',{},'No additional connections are bundled for this word.'));
  grid.append(connect);card.append(grid);

  const actions=el('div',{class:'teachactions'});
  const status=el('span',{class:'micro'},'Bundled locally — no dictionary lookup is needed.');
  const check=el('button',{class:'btn primary',id:'quickCheckBtn'},'Quick meaning check →');
  check.onclick=()=>showLearningCheck(word,story);
  actions.append(status,check);card.append(actions);
}
function storyPanel(title,id,text,loading=false){const p=el('div',{class:'storypanel'});p.append(el('h4',{},title),el('p',{id,class:loading?'loading':''},text));return p}
function hydrateStory(word,story){
  const meaning=document.getElementById('storyMeaning'),ety=document.getElementById('storyEtymology'),ex=document.getElementById('storyExample'),ph=document.getElementById('storyPhonetic'),status=document.getElementById('storyStatus');
  if(meaning){meaning.classList.remove('loading');meaning.textContent=story.definition||story.relation||'No definition was returned; use the source relationship below.'}
  if(ety){ety.classList.remove('loading');ety.textContent=story.etymology||'Etymology was not available in this lookup.';if(story.etymologySource)ety.parentElement.append(sourceLink(story.etymologySource,'Wiktionary'))}
  if(ex){ex.classList.remove('loading');ex.textContent=story.example||'No cited/example sentence was available for this entry.';if(story.example)ex.classList.add('quote');if(story.exampleSource)ex.parentElement.append(sourceLink(story.exampleSource,story.exampleSourceLabel||'source'))}
  if(ph)ph.textContent=[story.partOfSpeech,story.phonetic].filter(Boolean).join(' · ')||'Tap “Hear it” for browser pronunciation';
  if(status)status.textContent=story.networkOk?'Bundled lexical data loaded.':'Bundled lexical data is unavailable for this item.';
}
function sourceLink(url,label){const foot=el('div',{class:'sourcefoot'},'Source: '),a=el('a',{href:url,target:'_blank',rel:'noopener'},label);foot.append(a);return foot}
function showLearningCheck(word,story){
  if(!lesson||lesson.checked[word])return;
  lesson.checked[word]=true;
  const card=document.getElementById('learnCard'),box=el('div',{class:'checkbox'}),clue=story.quizDefinition||story.definition||story.relation||localStory(word).sourceCue||'the word you just studied';
  box.append(el('h4',{},'One quick check'),el('p',{},'Which word best matches this clue?'),el('div',{class:'prompt'},clue));
  const options=el('div',{class:'options'}),choices=learningDistractors(word,3);choices.push(word);
  for(const w of shuffle(choices)){
    const b=el('button',{class:'option',type:'button'},w);b.onclick=()=>{
      if(box.dataset.done)return;
      box.dataset.done='1';
      const ok=w===word;
      const buttons=[...options.children];
      for(const x of buttons){
        x.disabled=true;
        if(x.textContent===word)x.classList.add('correct');
      }
      b.classList.add(ok?'selected':'wrong');
      const fb=el('div',{class:'check-feedback '+(ok?'goodtxt':'badtxt')},
        ok?'Yes — that is '+word+'.':'Not quite. The match is '+word+'. Nothing is lost; the correct answer is highlighted.');
      box.append(fb);
      markIntroduced(word);
      const next=el('button',{class:'btn primary',type:'button',style:'margin-top:12px'},lesson.index===lesson.words.length-1?'Finish lesson':'Next word →');
      next.onclick=()=>{if(!lesson)return;lesson.index++;renderLessonWord()};
      box.append(next);
      next.focus();
    };options.append(b);
  }
  box.append(options);card.append(box);box.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function learningDistractors(word,n){
  const src=SOURCE_INFO[word],avoid=new Set([word,...(src?.neighbors||[])]);const qnums=src?.questions||WORD_META[word]?.questionNumbers||[];let pool=[];
  for(const qn of qnums){const q=QUESTIONS.find(x=>x.n===qn);if(q)pool.push(...q.options.filter(x=>!avoid.has(x)))}
  pool=[...new Set([...pool,...shuffle(ALL_WORDS.filter(x=>!avoid.has(x)))])];return pool.slice(0,n);
}
function markIntroduced(word){
  const x=state.learn[word]||{introduced:false,exposures:0};const first=!x.introduced;x.introduced=true;x.exposures=(x.exposures||0)+1;x.lastSeen=Date.now();state.learn[word]=x;if(first)state.xp+=2;save();
}
function finishLesson(){
  document.getElementById('learnBar').style.width='100%';const card=document.getElementById('learnCard'),words=[...lesson.words];card.innerHTML='';card.append(el('div',{class:'eyebrow'},'LESSON COMPLETE'),el('div',{class:'prompt'},'You gave '+words.length+' words a first set of retrieval cues.'),el('p',{class:'lede'},'A good next step is a short review while the material is still fresh; later successful retrievals will push it farther apart.'));
  const row=el('div',{class:'actions'}),review=el('button',{class:'btn primary'},'Review these words now'),more=el('button',{class:'btn'},'Learn another set'),home=el('button',{class:'btn ghost'},'Home');review.onclick=()=>{lesson=null;startSession('full',words)};more.onclick=startLesson;home.onclick=()=>{lesson=null;switchView('home')};row.append(review,more,home);card.append(row);updateDashboard();
}

// ---------- Bundled lexical enrichment ----------
function staticWordStory(word){
  const local=localStory(word),d=STATIC_WORD_DATA[word]||{};
  return {
    word,
    definition:d.definition||local.definition||local.relation||'',
    quizDefinition:d.quizDefinition||d.definition||local.definition||local.relation||'',
    rawDictionaryDefinition:d.rawDictionaryDefinition||'',
    sourceDefinition:d.sourceDefinition||local.definition||'',
    relation:local.relation,
    neighbors:local.neighbors||[],
    partOfSpeech:d.partOfSpeech||'',
    ipa:Array.isArray(d.ipa)?d.ipa:[],
    phonetic:Array.isArray(d.ipa)&&d.ipa.length?d.ipa[0]:'',
    audio:d.audio||'',
    etymology:d.etymology||'',
    etymologyBrief:d.etymologyBrief||'',
    example:d.example||'',
    exampleCitation:d.exampleCitation||'',
    synonyms:Array.isArray(d.synonyms)?d.synonyms:[],
    related:Array.isArray(d.related)?d.related:[],
    usageLabels:Array.isArray(d.usageLabels)?d.usageLabels:[],
    sourceNeighbors:Array.isArray(d.sourceNeighbors)?d.sourceNeighbors:[],
    courseSynonyms:Array.isArray(d.courseSynonyms)?d.courseSynonyms:[],
    courseCue:d.courseCue||'',
    modernUses:Array.isArray(d.modernUses)?d.modernUses:[],
    encounters:Array.isArray(d.encounters)?d.encounters:[],
    sourceQuestions:Array.isArray(d.sourceQuestions)?d.sourceQuestions:[],
    entryAvailable:!!d.entryAvailable,
    sourceCue:local.sourceCue
  };
}
async function getWordStory(word){return staticWordStory(word)}
function playWordAudio(word,story){
  const audio=story?.audio;
  if(audio){
    new Audio(audio.startsWith('//')?'https:'+audio:audio).play().catch(()=>speakWord(word));
  }else speakWord(word);
}

// ---------- Review mode ----------
async function renderCard(){
  if(!session)return;if(session.index>=session.queue.length)return finishSession();
  const entry=session.queue[session.index];session.assisted=false;session.locked=false;document.getElementById('gameCount').textContent=(session.index+1)+' / '+session.queue.length;document.getElementById('sessionBar').style.width=(100*session.index/session.queue.length)+'%';
  if(entry.deck==='core')renderCore(entry.id);else await renderFull(entry.id);
}
function coreQ(id){return QUESTIONS.find(q=>q.id===id)}
function correctWords(q){return q.correct.map(i=>q.options[i])}
function coreMode(q,p){if(p.stage>=4)return 'typed';if(p.stage>=3&&q.pick===1)return 'typed';return 'choice'}
function renderCore(id){
  const q=coreQ(id),p=prog('core',id),mode=coreMode(q,p);document.getElementById('modePill').textContent=mode==='typed'?'GENERATE':'DISCRIMINATE';const card=document.getElementById('gameCard');card.innerHTML='';
  card.append(el('div',{class:'micro'},'Source item '+q.n+' · '+stageName(p.stage)+(p.attempts?' · '+fmtDue(p.due):'')),el('div',{class:'prompt'},q.prompt));if(mode==='choice')renderCoreChoices(card,q,p);else renderCoreTyped(card,q,p);
}
function renderCoreChoices(card,q,p){
  card.append(el('div',{class:'hintline'},q.pick===1?'Choose one.':`Choose ${q.pick}.`));const opts=el('div',{class:'options'});let selected=[];
  q.options.forEach((txt,i)=>{const b=el('button',{class:'option',type:'button'},txt);b.onclick=()=>{if(session.locked)return;if(q.pick===1){selected=[i];[...opts.children].forEach(x=>x.classList.remove('selected'));b.classList.add('selected');submitCore(q,selected,false)}else{if(selected.includes(i)){selected=selected.filter(x=>x!==i);b.classList.remove('selected')}else if(selected.length<q.pick){selected.push(i);b.classList.add('selected')}submit.disabled=selected.length!==q.pick}};opts.append(b)});card.append(opts);
  if(q.pick>1){var submit=el('button',{class:'btn primary',type:'button',disabled:true,style:'margin-top:12px'},'Check answer');submit.onclick=()=>submitCore(q,selected,false);card.append(submit)}
}
function renderCoreTyped(card,q,p){
  const wrap=el('div',{class:'typed'}),input=el('input',{type:'text',autocomplete:'off',spellcheck:'false',placeholder:q.pick>1?`Type ${q.pick} answers, separated by commas`:'Type the word'}),check=el('button',{class:'btn primary'},'Check');wrap.append(input,check);card.append(wrap);
  const help=el('button',{class:'btn ghost',style:'margin-top:8px'},'Need choices');help.onclick=()=>{session.assisted=true;renderCoreChoices(card,q,p);wrap.remove();help.remove()};card.append(help);
  const go=()=>{const parts=input.value.split(/[,;]+/).map(x=>x.trim()).filter(Boolean);if(parts.length)submitCore(q,parts,true)};check.onclick=go;input.addEventListener('keydown',e=>{if(e.key==='Enter')go()});setTimeout(()=>input.focus(),0);
}
function submitCore(q,answer,isTyped){if(session.locked)return;session.locked=true;const expected=correctWords(q),ok=isTyped?setEq(answer,expected):(answer.length===q.correct.length&&answer.every(i=>q.correct.includes(i)));recordResult('core',q.id,ok,session.assisted);showFeedback({ok,expected,detail:q.prompt,deck:'core',id:q.id})}

async function renderFull(word){
  const p=prog('full',word),card=document.getElementById('gameCard');document.getElementById('modePill').textContent=p.stage>=3?'GENERATE':'RECOGNIZE';const local=localStory(word);
  card.innerHTML='';card.append(el('div',{class:'micro'},'Full lexicon · '+stageName(p.stage)),el('div',{class:'prompt'},local.definition||local.relation||'Loading a meaning cue…'));
  const story=staticWordStory(word);if(!session||session.queue[session.index]?.id!==word)return;card.innerHTML='';card.append(el('div',{class:'micro'},'Full lexicon · '+stageName(p.stage)+(story.partOfSpeech?' · '+story.partOfSpeech:'')));
  const clue=story.definition||story.relation||story.sourceCue;if(!clue){card.append(el('div',{class:'prompt'},word),el('div',{class:'feedback bad'},'A usable meaning cue was not available after the lookup timeout. This card will be skipped.'));const b=el('button',{class:'btn',style:'margin-top:12px'},'Continue');b.onclick=()=>{session.index++;renderCard()};card.append(b);return}
  card.append(el('div',{class:'prompt'},clue));if(p.stage>=3)renderFullTyped(card,word,story);else renderFullChoices(card,word,story);
}
function fullDistractors(word){return learningDistractors(word,3)}
function renderFullChoices(card,word,d){const choices=shuffle([word,...fullDistractors(word)]),opts=el('div',{class:'options'});choices.forEach(w=>{const b=el('button',{class:'option'},w);b.onclick=()=>submitFull(word,w===word,d);opts.append(b)});card.append(opts)}
function renderFullTyped(card,word,d){const wrap=el('div',{class:'typed'}),input=el('input',{type:'text',autocomplete:'off',spellcheck:'false',placeholder:'Type the word'}),check=el('button',{class:'btn primary'},'Check');wrap.append(input,check);card.append(wrap);const help=el('button',{class:'btn ghost',style:'margin-top:8px'},'Need choices');help.onclick=()=>{session.assisted=true;wrap.remove();help.remove();renderFullChoices(card,word,d)};card.append(help);const go=()=>{if(input.value.trim())submitFull(word,normalize(input.value)===normalize(word),d)};check.onclick=go;input.onkeydown=e=>{if(e.key==='Enter')go()};setTimeout(()=>input.focus(),0)}
function submitFull(word,ok,d){if(session.locked)return;session.locked=true;recordResult('full',word,ok,session.assisted);showFeedback({ok,expected:[word],detail:(d.partOfSpeech?d.partOfSpeech+' · ':'')+(d.definition||d.relation||''),deck:'full',id:word,audio:d.audio,story:d})}

function recordResult(deck,id,ok,assisted){
  const p=prog(deck,id);p.attempts++;p.last=Date.now();if(ok&&!assisted){p.correct++;p.stage=Math.min(8,p.stage+1);p.due=Date.now()+INTERVALS[p.stage];state.xp+=8+2*p.stage;session.correct++}else if(ok&&assisted){p.correct++;p.stage=Math.max(0,p.stage-1);p.due=Date.now()+10*60*1000;state.xp+=2}else{p.lapses++;p.stage=Math.max(0,p.stage-2);p.due=Date.now()+3*60*1000}
  session.answered++;state.history.push({t:Date.now(),deck,id,correct:!!ok,assisted:!!assisted});if(state.history.length>500)state.history=state.history.slice(-500);
  if((!ok||assisted)&&(session.retries[deck+':'+id]||0)<1){session.retries[deck+':'+id]=(session.retries[deck+':'+id]||0)+1;session.queue.splice(Math.min(session.index+4,session.queue.length),0,{deck,id,retry:true})}save();
}
function showFeedback({ok,expected,detail,deck,id,audio,story}){
  const card=document.getElementById('gameCard'),f=el('div',{class:'feedback '+(ok?'good':'bad')});f.append(el('strong',{class:ok?'goodtxt':'badtxt'},ok?(session.assisted?'Correct with help':'Correct'):'Not yet'),el('div',{class:'answerline'},expected.join(' · ')),el('p',{},detail));
  if(story?.etymology)f.append(el('p',{},'Word history cue: '+story.etymology.slice(0,240)+(story.etymology.length>240?'…':'')));if(!ok||session.assisted)f.append(el('p',{},'This item will return after a short lag.'));
  if(deck==='full'){const speak=el('button',{class:'btn mini secondary'},'Hear word');speak.onclick=()=>{if(audio){new Audio(audio.startsWith('//')?'https:'+audio:audio).play().catch(()=>speakWord(id))}else speakWord(id)};f.append(speak)}card.append(f);
  const row=el('div',{class:'gameactions'}),next=el('button',{class:'btn primary'},'Next →');next.onclick=()=>{session.index++;renderCard()};row.append(el('span',{class:'micro'},'Stage: '+stageName(prog(deck,id).stage)+' · next '+fmtDue(prog(deck,id).due)),next);card.append(row);next.focus();
}
function finishSession(){
  document.getElementById('sessionBar').style.width='100%';const card=document.getElementById('gameCard'),pct=session.answered?Math.round(100*session.correct/session.answered):0;card.innerHTML='';card.append(el('div',{class:'eyebrow'},'REVIEW COMPLETE'),el('div',{class:'prompt'},`${session.correct} solid retrievals`),el('p',{class:'lede'},`${pct}% of attempts were correct without help. Misses return sooner; successful items move farther out.`));const row=el('div',{class:'actions'}),again=el('button',{class:'btn primary'},'Review again'),learn=el('button',{class:'btn secondary'},'Learn new words'),home=el('button',{class:'btn ghost'},'Home');again.onclick=()=>startSession('review');learn.onclick=()=>{session=null;switchView('learn')};home.onclick=()=>{session=null;switchView('home')};row.append(again,learn,home);card.append(row);updateDashboard();
}

// ---------- Word bank ----------
function renderWords(){
  const grid=document.getElementById('wordGrid'),q=normalize(document.getElementById('wordSearch').value);grid.innerHTML='';let words=wordRandom||ALL_WORDS.filter(w=>normalize(w).includes(q));words=words.slice(0,wordPage);if(!words.length){grid.append(el('div',{class:'empty'},'No matching words.'));return}
  for(const w of words){const p=state.full[w],meta=WORD_META[w]||{},c=el('div',{class:'wordcard'});c.append(el('h4',{},w),el('div',{class:'wordmeta'},(state.learn[w]?.introduced?'introduced':'not yet learned')+(p?.attempts?(' · stage '+p.stage+' · '+fmtDue(p.due)):'')+(meta.questionNumbers?.length?' · Q'+meta.questionNumbers.join(', Q'):'')));
    const def=el('div',{class:'definition'});const staticStory=staticWordStory(w);def.textContent=staticStory.definition||staticStory.relation||localStory(w).sourceCue||'';c.append(def);
    const row=el('div',{class:'minirow'}),storyBtn=el('button',{class:'btn mini'},'Word story'),learnBtn=el('button',{class:'btn mini secondary'},state.learn[w]?.introduced?'Relearn':'Learn');
    storyBtn.onclick=()=>{const d=staticWordStory(w);def.textContent=d.definition||d.relation||'No meaning cue is bundled for this word.'};
    learnBtn.onclick=()=>{lesson={scope:'custom',words:[w],index:0,stories:{},checked:{}};document.getElementById('learnEmpty').classList.add('hidden');document.getElementById('learnStage').classList.remove('hidden');switchView('learn');renderLessonWord()};row.append(storyBtn,learnBtn);c.append(row);grid.append(c)}
}
function safeId(s){return s.replace(/[^a-z0-9]/gi,'_')}
document.getElementById('wordSearch').oninput=()=>{wordRandom=null;wordPage=60;renderWords()};document.getElementById('moreWords').onclick=()=>{wordRandom=null;wordPage+=60;renderWords()};document.getElementById('shuffleWords').onclick=()=>{wordRandom=shuffle(ALL_WORDS).slice(0,30);renderWords()};

// ---------- Pigeon Plaza ----------
function pigeonSVG(p,small=false){
  const gid='pg_'+p.id;
  const palette={
    1:['#91a3b2','#7f929f','#67b59f'],
    2:['#9aa9b8','#8798a5','#69b8a4'],
    3:['#8fa3b5','#7c91a0','#67b59f'],
    4:['#93a5b4','#7e929f','#69b8a4'],
    5:['#8d9fb4','#75899f','#6ec1ad'],
    6:['#8d9cb0','#74869a','#63b5a2'],
    7:['#8d7be8','#5d69a9','#69d0b2']
  }[p.style]||['#91a3b2','#7f929f','#67b59f'];
  const [body,wing,neck]=palette;
  const defs=p.style===7?`<defs><radialGradient id='${gid}_body' cx='40%' cy='28%'><stop offset='0' stop-color='#baf2e4'/><stop offset='.48' stop-color='#8d7be8'/><stop offset='1' stop-color='#465783'/></radialGradient></defs>`:'';
  const bodyFill=p.style===7?`url(#${gid}_body)`:body;
  const behind={
    3:`<path d='M48 79 Q80 62 112 79 L118 117 Q80 137 42 117 Z' fill='#f2c84f' opacity='.98'/>`,
    6:`<path d='M43 78 Q31 103 45 128 L61 116 L80 130 L99 116 L116 128 Q129 103 117 78 Q102 90 80 91 Q58 90 43 78 Z' fill='#7b4f7e' opacity='.9'/>`
  }[p.style]||'';
  const front={
    1:`<circle cx='35' cy='132' r='4' fill='#d8a950'/><circle cx='46' cy='136' r='3.2' fill='#e5bd69'/><circle cx='27' cy='138' r='2.7' fill='#c99342'/>`,
    2:`<path d='M54 76 Q80 86 107 76' fill='none' stroke='#ef7f70' stroke-width='10' stroke-linecap='round'/><path d='M96 80 L109 105' stroke='#ef7f70' stroke-width='8' stroke-linecap='round'/><path d='M102 101 l10 5 M104 108 l9 5' stroke='#ffd2cb' stroke-width='2'/>`,
    3:`<path d='M53 83 Q80 74 107 83 L111 117 Q80 129 49 117 Z' fill='#f4c74f'/><path d='M63 84 v32 M97 84 v32' stroke='#e2af2e' stroke-width='2'/><circle cx='80' cy='96' r='2.8' fill='#d4912b'/><path d='M58 47 Q80 26 103 47' fill='none' stroke='#f4c74f' stroke-width='8' stroke-linecap='round'/>`,
    4:`<path d='M48 30 L80 17 L114 31 L80 43 Z' fill='#39495c'/><path d='M108 31 v18' stroke='#39495c' stroke-width='3'/><circle cx='108' cy='51' r='3' fill='#efb94e'/><circle cx='69' cy='51' r='10' fill='none' stroke='#34495d' stroke-width='2.6'/><circle cx='91' cy='51' r='10' fill='none' stroke='#34495d' stroke-width='2.6'/><path d='M79 51 h2' stroke='#34495d' stroke-width='3'/>`,
    5:`<path d='M60 48 l4 -8 4 8 8 -2 -5 7 5 7 -8 -2 -4 8 -4 -8 -8 2 5 -7 -5 -7 Z M88 48 l4 -8 4 8 8 -2 -5 7 5 7 -8 -2 -4 8 -4 -8 -8 2 5 -7 -5 -7 Z' fill='#f48fb1'/><circle cx='123' cy='33' r='3' fill='#f4c74f'/><path d='M123 24 v18 M114 33 h18' stroke='#f4c74f' stroke-width='2'/>`,
    6:`<path d='M51 33 L58 16 L69 29 L80 12 L91 29 L102 16 L109 35 Z' fill='#f4c74f' stroke='#d69e2d' stroke-width='2'/><circle cx='59' cy='25' r='2.6' fill='#8d7be8'/><circle cx='80' cy='20' r='2.6' fill='#ef7f70'/><circle cx='101' cy='25' r='2.6' fill='#4eb89f'/>`,
    7:`<path d='M48 32 L56 13 L68 27 L80 8 L92 27 L104 13 L112 34 Z' fill='#ffe27a' stroke='#cfa93b' stroke-width='2'/><circle cx='57' cy='23' r='3' fill='#ef7f70'/><circle cx='80' cy='17' r='3' fill='#55c7b0'/><circle cx='103' cy='23' r='3' fill='#9a86ef'/><circle cx='128' cy='47' r='2.7' fill='#f9dc74'/><circle cx='28' cy='59' r='2.3' fill='#f5a8c3'/><circle cx='118' cy='103' r='2.2' fill='#b8f3e2'/><path d='M123 40 v14 M116 47 h14 M32 52 v13 M26 58 h12' stroke='#f8e59a' stroke-width='1.8'/>`
  }[p.style]||'';
  return `<svg viewBox='0 0 160 160' role='img' aria-label='${p.name}'>
    ${defs}${behind}
    <path d='M48 112 L29 129 L54 126 Z' fill='#687c8b'/>
    <path d='M112 112 L131 129 L106 126 Z' fill='#687c8b'/>
    <ellipse cx='80' cy='103' rx='42' ry='37' fill='${bodyFill}'/>
    <ellipse cx='51' cy='104' rx='18' ry='29' fill='${wing}' transform='rotate(14 51 104)'/>
    <ellipse cx='109' cy='104' rx='18' ry='29' fill='${wing}' transform='rotate(-14 109 104)'/>
    <ellipse cx='80' cy='76' rx='28' ry='27' fill='${neck}' opacity='.96'/>
    <circle cx='80' cy='52' r='27' fill='${bodyFill}'/>
    <circle cx='70' cy='48' r='5.2' fill='#fff'/><circle cx='90' cy='48' r='5.2' fill='#fff'/>
    <circle cx='71' cy='49' r='2.5' fill='#293a4c'/><circle cx='89' cy='49' r='2.5' fill='#293a4c'/>
    <path d='M72 59 L80 54 L88 59 L80 67 Z' fill='#e9aa49'/>
    <path d='M60 73 Q80 80 100 73' fill='none' stroke='#55b79f' stroke-width='4' stroke-linecap='round' opacity='.9'/>
    <path d='M65 131 v14 M95 131 v14' stroke='#c87965' stroke-width='3.4' stroke-linecap='round'/>
    <path d='M57 146 h15 M88 146 h15' stroke='#c87965' stroke-width='3.4' stroke-linecap='round'/>
    ${front}
  </svg>`;
}
function renderPigeonShop(){
  const shop=document.getElementById('pigeonShop');if(!shop||!state)return;
  const available=availableXP(),owned=state.pigeons||{};
  const sx=document.getElementById('shopXp'),ss=document.getElementById('shopSpent'),sf=document.getElementById('shopFlock');
  if(sx)sx.textContent=available.toLocaleString()+' XP';if(ss)ss.textContent=(state.xpSpent||0).toLocaleString()+' XP';if(sf)sf.textContent=Object.keys(owned).filter(k=>owned[k]).length+' / '+PIGEONS.length;
  shop.innerHTML='';
  for(const p of PIGEONS){
    const have=!!owned[p.id],fullLocked=p.requiresFull&&state.xp<FULL_XP_MILESTONE,canBuy=!have&&!fullLocked&&available>=p.price;
    const card=el('div',{class:'pigeon-card '+(have?'owned':(!canBuy?'locked':''))});
    card.append(el('span',{class:'rarity'},p.rarity));
    const art=el('div',{class:'pigeon-art'});art.innerHTML=pigeonSVG(p);card.append(art);
    card.append(el('h3',{},p.name),el('p',{},p.desc));
    if(p.requiresFull)card.append(el('div',{class:'full-xp-note'},'Requires '+FULL_XP_MILESTONE.toLocaleString()+' lifetime XP — the full-course milestone.'));
    const row=el('div',{class:'pigeon-price'}),price=el('strong',{},p.price.toLocaleString()+' XP');
    let b;
    if(have)b=el('button',{class:'btn mini secondary',disabled:true},'In your flock');
    else if(fullLocked)b=el('button',{class:'btn mini',disabled:true},'Full XP required');
    else if(available<p.price)b=el('button',{class:'btn mini',disabled:true},'Need '+(p.price-available).toLocaleString());
    else {b=el('button',{class:'btn mini primary'},'Adopt');b.onclick=()=>buyPigeon(p.id)}
    row.append(price,b);card.append(row);shop.append(card);
  }
}
function buyPigeon(id){
  const p=PIGEONS.find(x=>x.id===id);if(!p||state.pigeons?.[id])return;
  if(p.requiresFull&&state.xp<FULL_XP_MILESTONE){toast('This pigeon waits for the full-course XP milestone.');return}
  if(availableXP()<p.price){toast('Not enough spendable XP yet.');return}
  state.xpSpent=(state.xpSpent||0)+p.price;state.pigeons=state.pigeons||{};state.pigeons[id]=true;save();
  toast(p.name+' joined your flock.');
}
function renderHabitat(){
  const habitat=document.getElementById('pigeonHabitat'),perch=document.getElementById('pigeonPerch');if(!habitat||!perch||!state)return;
  const owned=PIGEONS.filter(p=>state.pigeons?.[p.id]);perch.innerHTML='';
  if(!owned.length){habitat.classList.add('hidden');return}
  habitat.classList.remove('hidden');
  for(const p of owned){const bird=el('div',{class:'perch-bird',title:p.name});bird.innerHTML=pigeonSVG(p,true);perch.append(bird)}
}

// ---------- Utilities/settings ----------
function el(tag,attrs={},text){const x=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')x.className=v;else if(k==='style')x.setAttribute('style',v);else if(k==='disabled')x.disabled=!!v;else x.setAttribute(k,v)}if(text!==undefined)x.textContent=text;return x}
function speakWord(word){if('speechSynthesis'in window){speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(word);u.rate=.86;speechSynthesis.speak(u)}}
function download(name,text,type='application/json'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
document.getElementById('exportBtn').onclick=()=>download('lexicon-forge-progress.json',JSON.stringify(state,null,2));
document.getElementById('importInput').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const x=JSON.parse(await f.text());if(x.version!==1)throw new Error('version');state=Object.assign(freshState(),x);state.learn=x.learn||{};state.enrich=x.enrich||{};save();toast('Progress imported.')}catch{toast('Could not import that progress file.')}};
document.getElementById('sessionSize').onchange=e=>{state.settings.sessionSize=Math.max(5,Math.min(30,Number(e.target.value)||12));save()};
document.getElementById('resetBtn').onclick=()=>{if(confirm('Reset all Lexicon Forge progress, XP purchases, and settings?')){state=freshState();save();renderWords();toast('Progress reset.')}};

async function init(){
  try{await loadData();state=loadState();updateDashboard()}catch(err){console.error(err);document.querySelector('main').innerHTML='<section class="view active"><div class="card"><h2>Could not load study data</h2><p class="lede">Lexicon Forge needs to be served over HTTP so it can load its local CSV files. On GitHub Pages this happens automatically.</p></div></section>'}
}
init();