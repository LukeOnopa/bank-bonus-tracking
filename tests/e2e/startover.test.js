const {expect,state,seed}=require('./helpers');
const P={state:'MN',ddCap:3000,splits:'3',transfers:true,cash:5000,pace:'2'};
async function withAccount(p){await p.goHome();await seed(p,P);const id=await p.evaluate(()=>window.__plan()[0].o.id);
 await seed(p,P,{[id]:{status:'open',opened:new Date().toISOString().slice(0,10),u:1}});return id}
async function startOver(p,keepAccounts){await p.click('nav [data-tab="mine"]');await p.locator('[data-act="wipe-ask"]').first().click();
 if(keepAccounts)await p.uncheck('#wipe-acc');await p.click('[data-act="wipe-do"]');await p.waitForTimeout(200)}
module.exports=[
{name:'Start over clears everything, and Undo brings it back',async fn({device}){const p=await device();const id=await withAccount(p);
 await startOver(p,false);let s=await state(p);
 expect(!s.profile.state&&!s.profile.intakeDone,'setup answers should be cleared');expect(!s.track[id]?.status,'tracked account should be cleared');
 expect(await p.isVisible('.intake select[data-k="state"]'),'should land on setup step 1');
 await p.click('#toast [data-act="undowipe"]');await p.waitForTimeout(200);
 s=await state(p);expect(s.profile.state==='MN'&&s.track[id]?.status==='open','Undo should restore answers and accounts')}},
{name:'Start over can keep tracked accounts',async fn({device}){const p=await device();const id=await withAccount(p);
 await startOver(p,true);const s=await state(p);
 expect(!s.profile.state,'answers should be cleared');expect(s.track[id]?.status==='open','open account should be kept')}},
];
