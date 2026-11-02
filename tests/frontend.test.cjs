const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('target save survives navigation without redirecting or touching removed elements', async () => {
  const {run,context,nodes,document}=app();
  const button={disabled:false},host={innerHTML:''};
  nodes['#save-targets']=button;nodes['#target-result']=host;
  document.querySelectorAll=()=>[{value:'75',dataset:{target:'attendance_rate'}}];
  let finishSave;
  context.fakeApi=url=>url==='/v1/setup'&& !finishSave ? new Promise(r=>finishSave=r) : Promise.resolve(url==='/v1/setup'?{config:{}}:{ready:true});
  run("state.user={role:'admin'};state.setup={config:{}};api=fakeApi");
  const saving=run('saveTargets()');
  assert.equal(button.disabled,true);
  delete nodes['#target-result'];
  finishSave({recalculated:true});
  await saving;
  assert.equal(button.disabled,false);
  assert.equal(run('state.dashboard.ready'),true);
});

test('out-of-range targets are blocked before sending a request', async () => {
  const {run,context,nodes,document}=app();
  nodes['#target-result']={innerHTML:''};nodes['#save-targets']={};
  document.querySelectorAll=()=>[{value:'101',dataset:{target:'attendance_rate'}}];
  context.fakeApi=()=>{throw Error('Must not send invalid target')};
  run("state.user={role:'admin'};api=fakeApi");
  await run('saveTargets()');
  assert.match(nodes['#target-result'].innerHTML,/0 to 100/);
});

test('structured validation errors display readable field messages', async () => {
  const {run,context}=app();
  context.fetch=async()=>({ok:false,json:async()=>({detail:[{loc:['body','password'],msg:'Field required'}]})});
  await assert.rejects(run("api('/test')"),/password: Field required/);
});

function app() {
  const nodes = {};
  const document = {
    querySelector: selector => nodes[selector] || null,
    querySelectorAll: () => [],
    createElement: () => ({})
  };
  const context = vm.createContext({document, console, FormData: class {}, setTimeout});
  const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8').replace(/start\(\);\s*$/, '');
  vm.runInContext(source, context);
  return {nodes, document, run: code => vm.runInContext(code, context), context};
}

test('new administrators follow CSV then targets; staff cannot upload', () => {
  const {run} = app();
  run("state.user={role:'admin'};state.setup={config:{onboarding:{setup_required:true,targets_confirmed:false}}}");
  assert.equal(run('needsSetup()'), true);
  assert.equal(run('visibleNavigation().length'), 2);
  run("state.setup.config.onboarding.targets_confirmed=true");
  assert.equal(run('needsSetup()'), false);
  assert.equal(run("visibleNavigation().some(x=>x[0]==='Overview')"), true);
  run("state.user={role:'viewer'}");
  assert.equal(run('canUpload()'), false);
  assert.equal(run("visibleNavigation().some(x=>x[0]==='Try a test CSV')"), false);
});

test('pagination, risk filter and student search work together', () => {
  const {run, nodes, document, context} = app();
  const search={value:''}, prev={}, next={}, status={};
  const control={querySelector:s=>({'input':search,'.previous':prev,'.next':next,'.page-status':status}[s])};
  const body={innerHTML:'',closest:()=>({before:()=>{}})};
  nodes['#prediction-rows']=body;nodes['#prediction-filter']={value:'all'};
  document.createElement=()=>control;
  context.records=Array.from({length:121},(_,i)=>({student_id:'S'+i,risk_band:i%2?'High':'Low',data_completeness:1}));
  run("installStudentTable(records,'prediction')");
  assert.equal(status.textContent,'1–50 of 121 students');
  assert.equal((body.innerHTML.match(/data-student=/g)||[]).length,50);
  next.onclick();
  assert.equal(status.textContent,'51–100 of 121 students');
  nodes['#prediction-filter'].value='High';nodes['#prediction-filter'].onchange();
  assert.equal(status.textContent,'1–50 of 60 students');
  search.value='S119';search.oninput();
  assert.equal(status.textContent,'1–1 of 1 students');
  assert.match(body.innerHTML,/data-student="S119"/);
  search.value='missing';search.oninput();
  assert.equal(status.textContent,'0 matching students');
  assert.equal(next.disabled,true);
});

test('zero and inactivity comparisons are truthful and finite', () => {
  const {run} = app();
  const html=run("signalEvidence([{field:'attendance_rate',label:'Attendance',value:0,target:.75,target_text:'75%',needs_review:true,direction:'below'},{field:'days_since_login',label:'Activity',value:0,target:0,target_text:'0 days',needs_review:false,direction:'above'}])");
  assert.match(html,/width:0%/);
  assert.match(html,/Within the maximum review target/);
  assert.doesNotMatch(html,/NaN|Infinity/);
});

test('read-only viewers cannot edit screening or cases', () => {
  const {run,context}=app();
  const input={disabled:false},button={removed:false,remove(){this.removed=true}};
  context.host={querySelectorAll:s=>s.startsWith('input')?[input]:[button]};
  run("state.user={role:'viewer'};applyReadOnly(host)");
  assert.equal(input.disabled,true);assert.equal(button.removed,true);
});

test('older student responses cannot replace the latest selected student', async () => {
  const {run,context,nodes}=app();
  const pending={};context.fakeApi=url=>new Promise(resolve=>pending[url]=resolve);
  nodes['#student-detail']={innerHTML:''};nodes['#save-screening']={};
  run("api=fakeApi;detailView=d=>d.student_id;updateProgress=()=>{};applyReadOnly=()=>{}");
  const first=run("loadStudent('A')"),second=run("loadStudent('B')");
  pending['/v1/students/B']({student_id:'B'});await second;
  pending['/v1/students/A']({student_id:'A'});await first;
  assert.equal(nodes['#student-detail'].innerHTML,'B');
});

test('student and case responses after navigation are safely ignored', async () => {
  const {run,context,nodes}=app();
  let resolve;context.fakeApi=()=>new Promise(r=>resolve=r);
  run('api=fakeApi');
  nodes['#student-detail']={innerHTML:''};
  let request=run("loadStudent('A')");
  delete nodes['#student-detail'];resolve({student_id:'A'});await request;
  nodes['#cases-content']={innerHTML:''};
  request=run('loadCases()');delete nodes['#cases-content'];resolve({});await request;
});

test('CSV header and student strings are escaped before displaying HTML', () => {
  const {run}=app();
  assert.equal(run("esc('<script>')"),'&lt;script&gt;');
  const html=run("predictionRows([{student_id:'<img src=x onerror=alert(1)>',risk_band:'High',data_completeness:1}])");
  assert.doesNotMatch(html,/<img /);
  assert.match(html,/&lt;img/);
});
