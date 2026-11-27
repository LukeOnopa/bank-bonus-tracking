const {expect,state,seed}=require('./helpers');
const P={state:'MN',ddCap:3000,splits:'3',transfers:true,cash:5000,pace:'2'};
const sel=id=>`#view select[data-act="status"][data-id="${id}"]`;
// cards fly to My accounts with an animation, so wait for them to leave instead of checking right away
const gone=(p,id)=>p.waitForFunction(s=>!document.querySelector(s),sel(id),{timeout:6000}).then(()=>true,()=>false);
module.exports=[
{name:'applying moves an offer from Find offers to My accounts, and it persists',async fn({device}){const p=await device();await p.goHome();await seed(p,P);
 await p.click('nav [data-tab="find"]');const first=p.locator('#view select[data-act="status"]').first();const id=await first.getAttribute('data-id');
 await first.selectOption('applied');
 expect(await gone(p,id),'offer should leave Find offers after applying');
 await p.click('nav [data-tab="mine"]');const mine=p.locator(sel(id));
 expect(await mine.count()>0,'offer should show in My accounts');
 await mine.first().selectOption('open');await p.waitForTimeout(300);
 await p.reload();const s=await state(p);expect(s.track[id]?.status==='open','status should be saved as open, got '+s.track[id]?.status)}},
{name:'denied and paid offers stay out of Find offers',async fn({device}){const p=await device();await p.goHome();await seed(p,P);
 await p.click('nav [data-tab="find"]');const ids=await p.locator('#view select[data-act="status"]').evaluateAll(x=>[...new Set(x.map(e=>e.dataset.id))].slice(0,2));
 await p.locator(sel(ids[0])).first().selectOption('denied');await gone(p,ids[0]);
 await p.locator(sel(ids[1])).first().selectOption('applied');await gone(p,ids[1]);
 await p.click('nav [data-tab="mine"]');const paid=p.locator(sel(ids[1])).first();
 const opts=await paid.locator('option').evaluateAll(o=>o.map(x=>x.value));const pv=opts.find(v=>v==='earned');expect(pv,'a paid status should exist: '+opts);
 await paid.selectOption(pv);
 // the "you got paid" animation holds redraws for a few seconds; the tab switch happens when it ends
 await p.click('nav [data-tab="find"]');await p.waitForSelector('#tabs [data-tab="find"][aria-selected="true"]',{timeout:8000});await p.waitForSelector('#view .findwrap');
 for(const id of ids)expect(await p.locator(sel(id)).count()===0,id+' should not be back in Find offers')}},
];
