const {expect,state,doSetup}=require('./helpers');
module.exports=[
{name:'blank answers are blocked and later steps stay locked',async fn({device}){const p=await device();await p.goHome();
 await p.click('nav [data-tab="mine"]');
 expect(await p.locator('[data-act="istep"][data-k="3"][disabled]').count()===1,'step 4 should be locked before step 1 is done');
 await p.click('#view .inav [data-act="inext"]');
 expect(/highlighted/i.test(await p.textContent('#view .inav')),'Next with blanks should say which questions are missing');
 expect(await p.locator('.iq.err').count()>0,'missing questions should be highlighted');
 expect(await p.locator('select[data-k="state"]').isVisible(),'should stay on step 1')}},
{name:'finishing all five steps saves the answers and shows a plan',async fn({device}){const p=await device();await p.goHome();
 await doSetup(p);const s=await state(p);
 expect(s.profile.intakeDone===true,'setup should be marked done');
 expect(s.profile.state==='MN'&&+s.profile.ddCap===3000&&+s.profile.pace===2,'answers should be saved: '+JSON.stringify(s.profile).slice(0,200));
 expect(!(await p.isVisible('.intake select[data-k="state"]')),'setup form should close after the last step');
 const plan=await p.evaluate(()=>window.__plan());expect(plan.length>0,'a plan should be suggested')}},
{name:'answers survive a reload',async fn({device}){const p=await device();await p.goHome();await doSetup(p,{state:'WI'});
 await p.reload();expect((await state(p)).profile.state==='WI','state answer lost after reload')}},
];
