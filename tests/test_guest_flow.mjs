import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const source=fs.readFileSync(new URL('../public/app.js',import.meta.url),'utf8').replace(/^import .*\n/,'').replace(/\ninit\(\);\s*$/,'');
function setup(){
 const handlers={},calls=[],memory=new Map(),app={innerHTML:'',addEventListener:(name,fn)=>handlers[name]=fn};
 const document={querySelector:s=>s==='#app'?app:null,querySelectorAll:()=>[],addEventListener(){},body:{dataset:{},style:{}}};
 const store={changed(){},flush:async()=>true,suspend(){},resume(){},complete(){}};
 const context=vm.createContext({document,crypto:webcrypto,location:{pathname:'/',origin:'https://test.local'},window:{addEventListener(){}},navigator:{},sessionStorage:{getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v)},createDraftStore:()=>store,prepareUpload:async f=>f,setTimeout(){},clearTimeout(){},requestAnimationFrame:fn=>fn(),Blob,TextEncoder,__request:async(url,options)=>{calls.push({url,options});return {expenseCount:1,totalAmount:99,submittedAt:'2026-11-21T00:00:00Z'}}});
 vm.runInContext(source+`;api=__request;globalThis.h={state,render,nextStep,blankExpense,restoreDraft};`,context);
 const h=context.h;h.state.config={maxFiles:12,maxFileSize:30*1024*1024,categories:[{id:'rail',label:'铁路'}]};return {...h,handlers,app,calls,memory};
}
test('welcome gates form until the guest confirms and keeps restored draft values',async()=>{
 const h=setup();h.state.applicant.name='已经填写的嘉宾';h.render();
 assert.match(h.app.innerHTML,/inert aria-hidden="true"/);assert.match(h.app.innerHTML,/填写前的温馨提示/);assert.match(h.app.innerHTML,/每笔费用的支付记录 · 必填/);
 await h.nextStep();assert.equal(h.calls.length,0);
 await h.handlers.click({target:{closest:()=>({dataset:{action:'accept-notice'}})}});
 assert.equal(h.state.noticeOpen,false);assert.equal(h.state.applicant.name,'已经填写的嘉宾');assert.doesNotMatch(h.app.innerHTML,/welcome-overlay/);
 assert.equal(h.memory.get('vip-welcome-20261121'),'1');
});
test('merged expense page rejects missing payment record before any submission',async()=>{
 const h=setup();h.state.noticeOpen=false;h.state.step=2;h.state.consent=true;
 h.state.expenses=[{...h.blankExpense(),fileId:'a'.repeat(32),category:'rail',amount:99}];
 await h.nextStep();assert.match(h.state.errors['expense-0-proof'],/至少 1 张/);assert.equal(h.calls.length,0);assert.equal(h.state.submissionReviewOpen,false);
});
test('valid merged page opens review confirmation and submits only after explicit confirmation',async()=>{
 const h=setup();h.state.noticeOpen=false;h.state.step=2;h.state.consent=true;h.state.applicant.mobile='13900000000';
 h.state.expenses=[{...h.blankExpense(),fileId:'a'.repeat(32),category:'rail',amount:99,paymentProofs:[{fileId:'b'.repeat(32)}]}];
 await h.nextStep();assert.equal(h.state.submissionReviewOpen,true);assert.equal(h.calls.length,0);assert.match(h.app.innerHTML,/提交前，再检查一下/);
 await h.nextStep(true);assert.equal(h.calls.length,1);assert.equal(h.calls[0].url,'/api/submissions');assert.equal(h.state.success.totalAmount,99);
 assert.match(h.app.innerHTML,/查看我的提交记录/);assert.match(h.app.innerHTML,/手机重新打开本网站/);
});
test('old confirmation-step drafts restore into the merged expense page',()=>{
 const h=setup();h.restoreDraft({authenticated:true,draft:{step:3,applicant:{name:'旧草稿'},payment:{method:'bank'},expenses:[]},uploads:[]});
 assert.equal(h.state.step,2);h.state.noticeOpen=false;h.render();assert.match(h.app.innerHTML,/整理您的费用与票据/);assert.match(h.app.innerHTML,/最后，再核对一下/);assert.doesNotMatch(h.app.innerHTML,/STEP 03 \/ 03/);
});
