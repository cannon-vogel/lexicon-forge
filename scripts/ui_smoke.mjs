#!/usr/bin/env node
import fs from 'node:fs/promises';
import { JSDOM } from 'jsdom';

const [html, app, questionsCSV, termsCSV, wordDataText] = await Promise.all([
  fs.readFile('index.html','utf8'),
  fs.readFile('app.js','utf8'),
  fs.readFile('questions.csv','utf8'),
  fs.readFile('terms.csv','utf8'),
  fs.readFile('word_data.json','utf8')
]);
const wordData=JSON.parse(wordDataText);

function parseCSV(text){
  const rows=[];let row=[],field='',quoted=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(quoted){
      if(c==='"'&&text[i+1]==='"'){field+='"';i++}
      else if(c==='"')quoted=false;
      else field+=c;
    }else{
      if(c==='"')quoted=true;
      else if(c===','){row.push(field);field=''}
      else if(c==='\n'){row.push(field);rows.push(row);row=[];field=''}
      else if(c!=='\r')field+=c;
    }
  }
  if(field.length||row.length){row.push(field);rows.push(row)}
  return rows;
}
async function waitFor(fn,label,timeout=2500){
  const start=Date.now();
  while(Date.now()-start<timeout){
    const v=fn(); if(v)return v;
    await new Promise(r=>setTimeout(r,10));
  }
  throw new Error('Timed out waiting for '+label);
}
function assert(cond,msg){if(!cond)throw new Error(msg)}

const dom=new JSDOM(html,{url:'http://lexicon.test/',runScripts:'outside-only',pretendToBeVisual:true});
const {window}=dom;
const {document}=window;
const errors=[];
window.addEventListener('error',e=>errors.push(e.error||new Error(e.message)));
const originalError=window.console.error.bind(window.console);
window.console.error=(...args)=>{errors.push(new Error(args.map(String).join(' ')));originalError(...args)};
window.scrollTo=()=>{};
window.HTMLElement.prototype.scrollIntoView=()=>{};
window.confirm=()=>true;
window.Audio=class{play(){return Promise.resolve()}};
window.speechSynthesis={cancel(){},speak(){}};
window.SpeechSynthesisUtterance=class{constructor(text){this.text=text}};
window.URL.createObjectURL=()=> 'blob:test';
window.URL.revokeObjectURL=()=>{};

window.fetch=async input=>{
  const url=String(input);
  const file=url.split('/').pop();
  if(file==='questions.csv')return {ok:true,text:async()=>questionsCSV};
  if(file==='terms.csv')return {ok:true,text:async()=>termsCSV};
  if(file==='word_data.json')return {ok:true,json:async()=>wordData};
  return {ok:false,status:404,text:async()=>'',json:async()=>({})};
};

window.localStorage.setItem('lexiconForge.v1',JSON.stringify({
  version:1,xp:1000,xpSpent:0,pigeons:{},core:{},full:{},dict:{},enrich:{},learn:{},history:[],settings:{sessionSize:12}
}));

window.eval(app);
await waitFor(()=>document.getElementById('xpTop')?.textContent==='1000','app initialization');

// 1. Wrong quick-check answer must give feedback and allow advancing.
document.getElementById('learnBtn').click();
const firstWord=await waitFor(()=>document.querySelector('#learnCard .wordhero h2')?.textContent,'first learning card');
const firstData=wordData.words[firstWord];
assert(firstData,'First learning word missing from bundled word_data.json');
assert(document.getElementById('storyEtymology')?.textContent===firstData.etymologyBrief,'Lesson did not render the bundled learner etymology');
const encounterCards=[...document.querySelectorAll('#learnCard .encounter')];
assert(encounterCards.length===2,'Lesson did not render two encounter cards');
assert(encounterCards.every(c=>c.querySelector('.encounter-label')?.textContent.trim()),'Encounter place label missing');
assert(encounterCards.every(c=>c.querySelector('.encounter-phrase')?.textContent.includes('Try it:')),'Encounter phrase label missing');
document.getElementById('quickCheckBtn').click();
await waitFor(()=>document.querySelectorAll('#learnCard .checkbox .option').length===4,'quick-check choices');
let options=[...document.querySelectorAll('#learnCard .checkbox .option')];
const wrong=options.find(b=>b.textContent!==firstWord);
assert(wrong,'No wrong quick-check option was available');
wrong.click();
await waitFor(()=>document.querySelector('#learnCard .check-feedback.badtxt'),'wrong-answer feedback');
const nextAfterWrong=[...document.querySelectorAll('#learnCard .checkbox .btn.primary')].find(b=>/Next word|Finish lesson/.test(b.textContent));
assert(nextAfterWrong&&!nextAfterWrong.disabled,'Wrong quick-check answer did not expose an enabled next button');
assert(document.querySelector('#learnCard .option.wrong'),'Wrong selection was not visibly marked');
assert(document.querySelector('#learnCard .option.correct'),'Correct selection was not revealed after a miss');
nextAfterWrong.click();
const secondWord=await waitFor(()=>{
  const w=document.querySelector('#learnCard .wordhero h2')?.textContent;
  return w&&w!==firstWord?w:null;
},'advance after wrong quick-check');

// 2. Correct quick-check path must also advance.
document.getElementById('quickCheckBtn').click();
await waitFor(()=>document.querySelectorAll('#learnCard .checkbox .option').length===4,'second quick-check choices');
options=[...document.querySelectorAll('#learnCard .checkbox .option')];
const correct=options.find(b=>b.textContent===secondWord);
assert(correct,'Correct quick-check choice not found');
correct.click();
await waitFor(()=>document.querySelector('#learnCard .check-feedback.goodtxt'),'correct-answer feedback');
const nextAfterCorrect=[...document.querySelectorAll('#learnCard .checkbox .btn.primary')].find(b=>/Next word|Finish lesson/.test(b.textContent));
assert(nextAfterCorrect&&!nextAfterCorrect.disabled,'Correct quick-check answer did not expose an enabled next button');

// 3. A wrong source-deck answer must show feedback rather than freeze.
document.getElementById('coreBtn').click();
await waitFor(()=>document.querySelectorAll('#gameCard .option').length===5,'source-deck choices');
const rows=parseCSV(questionsCSV),header=rows.shift();
const idx=Object.fromEntries(header.map((x,i)=>[x,i]));
const r=rows[0],correctIndices=new Set(r[idx.correct_indices].split(';').filter(Boolean).map(Number));
const wrongIndex=[0,1,2,3,4].find(i=>!correctIndices.has(i));
const coreButtons=[...document.querySelectorAll('#gameCard .option')];
coreButtons[wrongIndex].click();
await waitFor(()=>document.querySelector('#gameCard .feedback.bad'),'source-deck wrong feedback');
assert(document.querySelector('#gameCard .gameactions .btn.primary'),'Source-deck miss did not expose Next');

// 4. Pigeon purchase must update wallet and habitat.
document.querySelector('button[data-view="pigeons"]').click();
await waitFor(()=>document.querySelectorAll('#pigeonShop .pigeon-card').length===7,'pigeon shop');
const adopt=document.querySelector('#pigeonShop .pigeon-card .btn.primary');
assert(adopt,'Affordable pigeon did not have an Adopt button');
adopt.click();
await waitFor(()=>document.getElementById('shopFlock')?.textContent==='1 / 7','pigeon adoption');
assert(document.getElementById('shopSpent').textContent==='75 XP','Pigeon purchase did not deduct 75 XP');
assert(!document.getElementById('pigeonHabitat').classList.contains('hidden'),'Purchased pigeon did not appear in habitat');

// Every shop bird must use the single shared pigeon head/body geometry.
// Accessories may add circles, but never another 27px head.
for(const card of document.querySelectorAll('#pigeonShop .pigeon-card')){
  const svg=card.querySelector('svg');
  assert(svg,'Pigeon SVG missing');
  assert(svg.querySelectorAll("circle[r='27']").length===1,'Pigeon does not have a single shared pigeon head');
  assert(svg.querySelectorAll("ellipse[cx='80'][cy='103']").length===1,'Pigeon does not have a single shared body');
}

// 5. No runtime error should have been raised by any tested interaction.
if(errors.length)throw errors[0];

console.log('UI smoke test passed:');
console.log('  learner etymology + two practical encounter cards render from static data');
console.log('  wrong quick-check -> feedback + correct reveal + next');
console.log('  correct quick-check -> feedback + next');
console.log('  wrong source-deck choice -> feedback + next');
console.log('  pigeon adoption -> wallet + habitat update');
console.log('  all pigeon accessories share one aligned head/body geometry');
