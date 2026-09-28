
'use strict';
let QUESTIONS=[];
let ALL_WORDS=[];
let WORD_META={};

function parseCSV(text){
  const rows=[]; let row=[],field='',quoted=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(quoted){
      if(c==='"'&&text[i+1]==='"'){field+='"';i++;}
      else if(c==='"') quoted=false;
      else field+=c;
    }else{
      if(c==='"') quoted=true;
      else if(c===','){row.push(field);field='';}
      else if(c==='\n'){row.push(field);rows.push(row);row=[];field='';}
      else if(c!=='\r') field+=c;
    }
  }
  if(field.length||row.length){row.push(field);rows.push(row);}
  return rows;
}

async function loadData(){
  const [qText,tText]=await Promise.all([
    fetch('questions.csv').then(r=>{if(!r.ok)throw new Error('questions.csv');return r.text()}),
    fetch('terms.csv').then(r=>{if(!r.ok)throw new Error('terms.csv');return r.text()})
  ]);
  const qr=parseCSV(qText), qh=qr.shift();
  const qi=Object.fromEntries(qh.map((h,i)=>[h,i]));
  QUESTIONS=qr.filter(r=>r.length>1).map(r=>({
    id:'q'+r[qi.question_number],
    n:Number(r[qi.question_number]),
    prompt:r[qi.prompt],
    block:r[qi.block],
    pick:Number(r[qi.pick]),
    options:[1,2,3,4,5].map(n=>r[qi['option_'+n]]),
    correct:r[qi.correct_indices].split(';').filter(Boolean).map(Number)
  }));
  const tr=parseCSV(tText), th=tr.shift();
  const ti=Object.fromEntries(th.map((h,i)=>[h,i]));
  for(const r of tr.filter(r=>r.length>1)){
    const term=r[ti.term]; if(!term)continue; ALL_WORDS.push(term);
    WORD_META[term]={occurrences:Number(r[ti.occurrences]||1),source:r[ti.source]||'',questionNumbers:String(r[ti.question_numbers]||'').split(';').map(x=>Number(x.trim())).filter(Boolean)};
  }
  ALL_WORDS.sort((a,b)=>a.localeCompare(b));
}
const KEY='lexiconForge.v1';
const DAY=86400000;
const INTERVALS=[0,5*60*1000,20*60*1000,DAY,3*DAY,7*DAY,14*DAY,30*DAY,90*DAY];
let state=null;
let session=null;
let wordPage=30;
let wordRandom=null;

function freshState(){return {version:1,xp:0,core:{},full:{},dict:{},history:[],settings:{sessionSize:12}}}
function loadState(){try{const x=JSON.parse(localStorage.getItem(KEY));return x&&x.version===1?Object.assign(freshState(),x):freshState()}catch{return freshState()}}
function save(){localStorage.setItem(KEY,JSON.stringify(state));updateDashboard()}
function prog(deck,id){const root=deck==='core'?state.core:state.full;return root[id]||(root[id]={stage:0,due:0,attempts:0,correct:0,lapses:0,last:0})}
function shuffle(a){a=[...a];for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
function normalize(s){return s.toLowerCase().trim().replace(/[’']/g,"'").replace(/[^a-z0-9' -]+/g,'').replace(/\s+/g,' ')}
function setEq(a,b){a=[...a].map(normalize).sort();b=[...b].map(normalize).sort();return a.length===b.length&&a.every((x,i)=>x===b[i])}
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>t.classList.remove('show'),2600)}
function level(){return Math.floor(Math.sqrt(state.xp/80))+1}
function stageName(s){return ['new','fresh','learning','1 day','3 days','1 week','2 weeks','1 month','3 months'][Math.min(s,8)]}
function fmtDue(ts){if(!ts||ts<=Date.now())return 'due';const d=ts-Date.now();if(d<3600000)return Math.ceil(d/60000)+'m';if(d<DAY)return Math.ceil(d/3600000)+'h';return Math.ceil(d/DAY)+'d'}
function recentAccuracy(){const h=state.history.slice(-60);if(!h.length)return null;return Math.round(100*h.filter(x=>x.correct).length/h.length)}
function countDue(root){const now=Date.now();return Object.values(root).filter(p=>p.attempts&&p.due<=now).length}
function countMastered(root){return Object.values(root).filter(p=>p.stage>=5).length}
function updateDashboard(){
  const cm=countMastered(state.core),fm=countMastered(state.full),due=countDue(state.core)+countDue(state.full),acc=recentAccuracy();
  document.getElementById('levelTop').textContent=level();document.getElementById('xpTop').textContent=state.xp;document.getElementById('dueTop').textContent=due;
  document.getElementById('coreMastered').textContent=cm;document.getElementById('fullMastered').textContent=fm;document.getElementById('reviewDue').textContent=due;document.getElementById('retention').textContent=acc===null?'—':acc+'%';
  document.getElementById('coreBar').style.width=(100*cm/QUESTIONS.length)+'%';
  document.getElementById('sessionSize').value=state.settings.sessionSize||12;
}

function switchView(id){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===id));document.querySelectorAll('.navbtn').forEach(b=>b.classList.toggle('active',b.dataset.view===id));if(id==='words')renderWords();window.scrollTo({top:0,behavior:'smooth'})}
document.querySelectorAll('.navbtn').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));

function dueSorted(ids,deck){const root=deck==='core'?state.core:state.full,now=Date.now();return ids.filter(id=>root[id]?.attempts&&root[id].due<=now).sort((a,b)=>root[a].due-root[b].due)}
function unseen(ids,deck){const root=deck==='core'?state.core:state.full;return ids.filter(id=>!root[id]?.attempts)}
function chooseCore(n){const ids=QUESTIONS.map(q=>q.id),root=state.core;let out=dueSorted(ids,'core');const seenFuture=ids.filter(id=>root[id]?.attempts&&root[id].due>Date.now()).sort((a,b)=>root[a].due-root[b].due);const fresh=unseen(ids,'core');out=[...out,...fresh,...seenFuture];return [...new Set(out)].slice(0,n)}
function chooseFull(n){const ids=ALL_WORDS;let out=dueSorted(ids,'full');const fresh=shuffle(unseen(ids,'full'));const future=ids.filter(id=>state.full[id]?.attempts&&state.full[id].due>Date.now()).sort((a,b)=>state.full[a].due-state.full[b].due);return [...new Set([...out,...fresh,...future])].slice(0,n)}
function chooseDaily(n){const dueCore=dueSorted(QUESTIONS.map(q=>q.id),'core');const dueFull=dueSorted(ALL_WORDS,'full');let q=[];for(const id of dueCore)q.push({deck:'core',id});for(const id of dueFull)q.push({deck:'full',id});const need=n-q.length;if(need>0){const coreFresh=chooseCore(Math.ceil(need*.7));for(const id of coreFresh)if(!q.some(x=>x.deck==='core'&&x.id===id))q.push({deck:'core',id});const fullFresh=chooseFull(n-q.length);for(const id of fullFresh)if(!q.some(x=>x.deck==='full'&&x.id===id))q.push({deck:'full',id})}return q.slice(0,n)}
function startSession(deck){const n=Number(state.settings.sessionSize)||12;let queue;if(deck==='core')queue=chooseCore(n).map(id=>({deck:'core',id}));else if(deck==='full')queue=chooseFull(n).map(id=>({deck:'full',id}));else queue=chooseDaily(n);session={queue,index:0,answered:0,correct:0,retries:{},assisted:false,locked:false};switchView('game');renderCard()}

document.getElementById('dailyBtn').onclick=()=>startSession('daily');
document.getElementById('coreBtn').onclick=()=>startSession('core');
document.getElementById('fullBtn').onclick=()=>startSession('full');
document.getElementById('quitBtn').onclick=()=>{session=null;switchView('home')};

async function renderCard(){
  if(!session)return;
  if(session.index>=session.queue.length){return finishSession()}
  const entry=session.queue[session.index];session.assisted=false;session.locked=false;
  document.getElementById('gameCount').textContent=(session.index+1)+' / '+session.queue.length;
  document.getElementById('sessionBar').style.width=(100*session.index/session.queue.length)+'%';
  if(entry.deck==='core')renderCore(entry.id);else await renderFull(entry.id);
}
function coreQ(id){return QUESTIONS.find(q=>q.id===id)}
function correctWords(q){return q.correct.map(i=>q.options[i])}
function coreMode(q,p){if(p.stage>=4)return 'typed';if(p.stage>=3&&q.pick===1)return 'typed';return 'choice'}
function renderCore(id){
  const q=coreQ(id),p=prog('core',id),mode=coreMode(q,p);document.getElementById('modePill').textContent=mode==='typed'?'GENERATE':'DISCRIMINATE';
  const card=document.getElementById('gameCard');card.innerHTML='';
  card.append(el('div',{class:'micro'},'Source item '+q.n+' · '+stageName(p.stage)+(p.attempts?' · '+fmtDue(p.due):'')));
  card.append(el('div',{class:'prompt'},q.prompt));
  if(mode==='choice')renderCoreChoices(card,q,p);else renderCoreTyped(card,q,p);
}
function renderCoreChoices(card,q,p){
  card.append(el('div',{class:'hintline'},q.pick===1?'Choose one.':`Choose ${q.pick}.`));
  const opts=el('div',{class:'options'});let selected=[];
  q.options.forEach((txt,i)=>{const b=el('button',{class:'option',type:'button'},txt);b.onclick=()=>{if(session.locked)return;if(q.pick===1){selected=[i];[...opts.children].forEach(x=>x.classList.remove('selected'));b.classList.add('selected');submitCore(q,selected,false)}else{if(selected.includes(i)){selected=selected.filter(x=>x!==i);b.classList.remove('selected')}else if(selected.length<q.pick){selected.push(i);b.classList.add('selected')}submit.disabled=selected.length!==q.pick}};opts.append(b)});card.append(opts);
  if(q.pick>1){var submit=el('button',{class:'btn primary',type:'button',disabled:true,style:'margin-top:12px'},'Check answer');submit.onclick=()=>submitCore(q,selected,false);card.append(submit)}
}
function renderCoreTyped(card,q,p){
  const answers=correctWords(q),wrap=el('div',{class:'typed'}),input=el('input',{type:'text',autocomplete:'off',spellcheck:'false',placeholder:q.pick>1?`Type ${q.pick} answers, separated by commas`:'Type the word'}),check=el('button',{class:'btn primary',type:'button'},'Check');
  wrap.append(input,check);card.append(wrap);const help=el('button',{class:'btn ghost',type:'button',style:'margin-top:8px'},'Need choices');help.onclick=()=>{session.assisted=true;renderCoreChoices(card,q,p);wrap.remove();help.remove()};card.append(help);
  const go=()=>{const parts=input.value.split(/[,;]+/).map(x=>x.trim()).filter(Boolean);if(!parts.length)return;submitCore(q,parts,true)};check.onclick=go;input.addEventListener('keydown',e=>{if(e.key==='Enter')go()});setTimeout(()=>input.focus(),0)
}
function submitCore(q,answer,isTyped){
  if(session.locked)return;session.locked=true;
  const expected=correctWords(q);let ok;
  if(isTyped)ok=setEq(answer,expected);else ok=answer.length===q.correct.length&&answer.every(i=>q.correct.includes(i));
  recordResult('core',q.id,ok,session.assisted);
  showFeedback({ok,expected,detail:q.prompt,deck:'core',id:q.id});
}

async function getDefinition(word){
  if(state.dict[word])return state.dict[word];
  const url='https://api.dictionaryapi.dev/api/v2/entries/en/'+encodeURIComponent(word);
  try{const res=await fetch(url);if(!res.ok)throw new Error('not found');const data=await res.json();let hit=null;for(const e of data){for(const m of e.meanings||[]){for(const d of m.definitions||[]){if(d.definition){hit={word,partOfSpeech:m.partOfSpeech||'',definition:d.definition,example:d.example||'',phonetic:e.phonetic||'',audio:(e.phonetics||[]).find(x=>x.audio)?.audio||''};break}}if(hit)break}if(hit)break}if(!hit)throw new Error('empty');state.dict[word]=hit;save();return hit}catch(e){state.dict[word]={word,error:true,definition:'Definition unavailable from Dictionary API.'};save();return state.dict[word]}
}
async function renderFull(word){
  const p=prog('full',word),card=document.getElementById('gameCard');document.getElementById('modePill').textContent=p.stage>=3?'GENERATE':'RECOGNIZE';card.innerHTML='<div class="micro">Loading dictionary entry for <b>'+escapeHtml(word)+'</b>…</div>';
  const d=await getDefinition(word);if(!session||session.queue[session.index]?.id!==word)return;
  if(d.error){card.innerHTML='';card.append(el('div',{class:'prompt'},word),el('div',{class:'feedback bad'},'No dictionary entry was returned for this term. This card will be skipped without affecting progress.'));const b=el('button',{class:'btn',style:'margin-top:12px'},'Continue');b.onclick=()=>{session.index++;renderCard()};card.append(b);return}
  card.innerHTML='';card.append(el('div',{class:'micro'},'Full lexicon · '+stageName(p.stage)+(d.partOfSpeech?' · '+d.partOfSpeech:'')));
  card.append(el('div',{class:'prompt'},d.definition));
  if(p.stage>=3)renderFullTyped(card,word,d);else renderFullChoices(card,word,d);
}
function fullDistractors(word){const pool=ALL_WORDS.filter(w=>w!==word);return shuffle(pool).slice(0,3)}
function renderFullChoices(card,word,d){const choices=shuffle([word,...fullDistractors(word)]),opts=el('div',{class:'options'});choices.forEach(w=>{const b=el('button',{class:'option'},w);b.onclick=()=>submitFull(word,w===word,d,false);opts.append(b)});card.append(opts)}
function renderFullTyped(card,word,d){const wrap=el('div',{class:'typed'}),input=el('input',{type:'text',autocomplete:'off',spellcheck:'false',placeholder:'Type the word'}),check=el('button',{class:'btn primary'},'Check');wrap.append(input,check);card.append(wrap);const help=el('button',{class:'btn ghost',style:'margin-top:8px'},'Need choices');help.onclick=()=>{session.assisted=true;wrap.remove();help.remove();renderFullChoices(card,word,d)};card.append(help);const go=()=>{if(!input.value.trim())return;submitFull(word,normalize(input.value)===normalize(word),d,true)};check.onclick=go;input.onkeydown=e=>{if(e.key==='Enter')go()};setTimeout(()=>input.focus(),0)}
function submitFull(word,ok,d){if(session.locked)return;session.locked=true;recordResult('full',word,ok,session.assisted);showFeedback({ok,expected:[word],detail:(d.partOfSpeech?d.partOfSpeech+' · ':'')+d.definition,deck:'full',id:word,audio:d.audio})}

function recordResult(deck,id,ok,assisted){
  const p=prog(deck,id);p.attempts++;p.last=Date.now();
  if(ok&&!assisted){p.correct++;p.stage=Math.min(8,p.stage+1);p.due=Date.now()+INTERVALS[p.stage];state.xp+=8+2*p.stage;session.correct++}
  else if(ok&&assisted){p.correct++;p.stage=Math.max(0,p.stage-1);p.due=Date.now()+10*60*1000;state.xp+=2}
  else{p.lapses++;p.stage=Math.max(0,p.stage-2);p.due=Date.now()+3*60*1000}
  session.answered++;state.history.push({t:Date.now(),deck,id,correct:!!ok,assisted:!!assisted});if(state.history.length>500)state.history=state.history.slice(-500);
  if((!ok||assisted)&&(session.retries[deck+':'+id]||0)<1){session.retries[deck+':'+id]=(session.retries[deck+':'+id]||0)+1;const at=Math.min(session.index+4,session.queue.length);session.queue.splice(at,0,{deck,id,retry:true})}
  save();
}
function showFeedback({ok,expected,detail,deck,id,audio}){
  const card=document.getElementById('gameCard');const f=el('div',{class:'feedback '+(ok?'good':'bad')});f.append(el('strong',{class:ok?'goodtxt':'badtxt'},ok?(session.assisted?'Correct with help':'Correct'):'Not yet'));
  f.append(el('div',{class:'answerline'},expected.join(' · ')));f.append(el('p',{},detail));
  if(!ok||session.assisted)f.append(el('p',{},'This item will return after a short lag. Try to retrieve it before looking back at this feedback.'));
  if(deck==='full'){const meta=WORD_META[id];if(meta?.questionNumbers?.length)f.append(el('p',{},'Source appearance: question '+meta.questionNumbers.join(', ')+'.'));const speak=el('button',{class:'btn mini',type:'button'},'Pronounce');speak.onclick=()=>{if(audio){new Audio(audio.startsWith('//')?'https:'+audio:audio).play().catch(()=>speakWord(id))}else speakWord(id)};f.append(speak)}
  card.append(f);const row=el('div',{class:'gameactions'}),next=el('button',{class:'btn primary'},'Next →');next.onclick=()=>{session.index++;renderCard()};row.append(el('span',{class:'micro'},'Stage: '+stageName(prog(deck,id).stage)+' · next '+fmtDue(prog(deck,id).due)),next);card.append(row);next.focus();
}
function finishSession(){document.getElementById('sessionBar').style.width='100%';const card=document.getElementById('gameCard'),pct=session.answered?Math.round(100*session.correct/session.answered):0;card.innerHTML='';card.append(el('div',{class:'micro'},'Run complete'),el('div',{class:'prompt'},`${session.correct} solid retrievals`),el('p',{class:'lede'},`${pct}% of attempts were correct without help. Misses were scheduled sooner; successful items moved farther into the future.`));const row=el('div',{class:'actions'}),again=el('button',{class:'btn primary'},'Start another run'),home=el('button',{class:'btn'},'Back to dashboard');again.onclick=()=>startSession('daily');home.onclick=()=>{session=null;switchView('home')};row.append(again,home);card.append(row);updateDashboard()}

function el(tag,attrs={},text){const x=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')x.className=v;else if(k==='style')x.setAttribute('style',v);else if(k==='disabled')x.disabled=!!v;else x.setAttribute(k,v)}if(text!==undefined)x.textContent=text;return x}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function speakWord(word){if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(word))}}

function renderWords(){const grid=document.getElementById('wordGrid'),q=normalize(document.getElementById('wordSearch').value);grid.innerHTML='';let words=wordRandom||ALL_WORDS.filter(w=>normalize(w).includes(q));words=words.slice(0,wordPage);if(!words.length){grid.append(el('div',{class:'empty'},'No matching words.'));return}for(const w of words){const p=state.full[w],meta=WORD_META[w]||{},c=el('div',{class:'wordcard'});c.append(el('h4',{},w),el('div',{class:'wordmeta'},(p?.attempts?('stage '+p.stage+' · '+fmtDue(p.due)):'unseen')+(meta.questionNumbers?.length?' · Q'+meta.questionNumbers.join(', Q'):'')));const def=el('div',{class:'definition',id:'def-'+safeId(w)});if(state.dict[w]&&!state.dict[w].error)def.textContent=state.dict[w].definition;c.append(def);const row=el('div',{class:'minirow'}),lookup=el('button',{class:'btn mini'},state.dict[w]?'Refresh':'Definition'),study=el('button',{class:'btn mini secondary'},'Study next');lookup.onclick=async()=>{def.innerHTML='<em>Loading…</em>';delete state.dict[w];const d=await getDefinition(w);def.textContent=d.definition};study.onclick=()=>{session={queue:[{deck:'full',id:w}],index:0,answered:0,correct:0,retries:{},assisted:false,locked:false};switchView('game');renderCard()};row.append(lookup,study);c.append(row);grid.append(c)}}
function safeId(s){return s.replace(/[^a-z0-9]/gi,'_')}
document.getElementById('wordSearch').oninput=()=>{wordRandom=null;wordPage=60;renderWords()};document.getElementById('moreWords').onclick=()=>{wordRandom=null;wordPage+=60;renderWords()};document.getElementById('shuffleWords').onclick=()=>{wordRandom=shuffle(ALL_WORDS).slice(0,30);renderWords()};

function download(name,text,type='application/json'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
document.getElementById('exportBtn').onclick=()=>download('lexicon-forge-progress.json',JSON.stringify(state,null,2));
document.getElementById('importInput').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const x=JSON.parse(await f.text());if(x.version!==1)throw new Error('version');state=Object.assign(freshState(),x);save();toast('Progress imported.')}catch{toast('Could not import that progress file.')}};
document.getElementById('sessionSize').onchange=e=>{state.settings.sessionSize=Math.max(5,Math.min(30,Number(e.target.value)||12));save()};
document.getElementById('resetBtn').onclick=()=>{if(confirm('Reset all Lexicon Forge progress and cached definitions?')){state=freshState();save();renderWords();toast('Progress reset.')}};

async function init(){
  try{
    await loadData();
    state=loadState();
    updateDashboard();
  }catch(err){
    console.error(err);
    document.querySelector('main').innerHTML='<section class="view active"><div class="card"><h2>Could not load study data</h2><p class="lede">Lexicon Forge needs to be served over HTTP so it can load its local CSV files. On GitHub Pages this happens automatically.</p></div></section>';
  }
}
init();