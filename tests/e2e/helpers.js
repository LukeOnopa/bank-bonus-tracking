// Shared steps for the browser tests.
function expect(cond,msg){if(!cond)throw new Error(msg)}
const state=page=>page.evaluate(()=>JSON.parse(localStorage.getItem('cbt')||'null'));

// Answer all five setup questions (My accounts tab). Options mirror the setup form.
async function doSetup(page,o={}){const a={state:'MN',branch:'1',mil:'0',ddCap:'3000',splits:'3',transfers:'1',cash:'5000',noHard:'1',noFee:'1',pace:'2',onlySure:'1',c12:'1',...o};
 await page.click('nav [data-tab="mine"]');
 const next=async()=>{await page.click('#view .inav [data-act="inext"], #view .inav [data-act="idone"]');await page.waitForTimeout(80)};
 // each answer redraws the form a moment later; wait for that before typing, or the redraw wipes the typed value
 const num=async(k,v)=>{await page.waitForTimeout(60);await page.fill(`input[data-k="${k}"]`,v);await page.dispatchEvent(`input[data-k="${k}"]`,'change')};
 const vis=sel=>page.waitForSelector(sel,{state:'attached',timeout:5000});
 await vis('select[data-k="state"]');
 await page.selectOption('select[data-k="state"]',a.state);await page.check(`input[name="branch"][value="${a.branch}"]`);await page.check(`input[name="mil"][value="${a.mil}"]`);await next();
 await vis('input[data-k="ddCap"]');await num('ddCap',a.ddCap);await page.selectOption('select[data-k="splits"]',a.splits);await page.check(`input[name="transfers"][value="${a.transfers}"]`);await next();
 await vis('input[data-k="cash"]');await num('cash',a.cash);await page.check(`input[name="noHard"][value="${a.noHard}"]`);await page.check(`input[name="noFee"][value="${a.noFee}"]`);await next();
 await vis('input[data-act="nobanks"]');await page.check('input[data-act="nobanks"]');await next();
 await vis('select[data-k="pace"]');await page.selectOption('select[data-k="pace"]',a.pace);await page.check(`input[name="onlySure"][value="${a.onlySure}"]`);await num('c12',a.c12);await next();
 try{await page.waitForFunction(()=>JSON.parse(localStorage.getItem('cbt')||'{}').profile?.intakeDone===true,null,{timeout:5000})}
 catch(e){const d=await page.evaluate(()=>({p:JSON.parse(localStorage.getItem('cbt')||'{}').profile,nav:document.querySelector('#view .inav')?.innerText,err:[...document.querySelectorAll('.iq.err')].map(x=>x.innerText.slice(0,60))}));
  throw new Error('Setup did not finish: '+JSON.stringify(d).slice(0,900))}}

// Seed the browser's saved data directly, then reload (faster than clicking through setup).
async function seed(page,profile,track={}){
 await page.evaluate(([p,t])=>localStorage.setItem('cbt',JSON.stringify({profile:{intakeDone:true,u:1,branch:true,mil:false,noHard:true,noFee:true,noBanks:true,banks:{},onlySure:true,chex:{c12:1},...p},track:t,custom:[],v:1})),[profile,track]);
 await page.reload();await page.waitForFunction(()=>document.querySelector('#view')?.children.length>0)}

module.exports={expect,state,doSetup,seed};
