const {expect,seed}=require('./helpers');
module.exports=[
{name:'"Where" lists states by name, and long lists open from the summary',async fn({device}){const p=await device({viewport:{width:390,height:844}});await p.goHome();
 await seed(p,{state:'MN',ddCap:3000,splits:'3',transfers:true,cash:5000,pace:'2'});await p.click('nav [data-tab="find"]');
 const d=p.locator('#view details.stl').first();expect(await d.count(),'an offer with many states should have a dropdown');
 expect(/\d+ states, including Minnesota/.test(await d.locator('summary').innerText()),'summary should name the user\'s state');
 expect(!(await d.evaluate(e=>e.open)),'list should start closed');await d.locator('summary').click();
 const names=await d.locator('li').allInnerTexts();expect(names.length>3&&names.includes('Minnesota'),'open list should show full state names: '+names);
 expect(await d.locator('li.me').innerText()==='Minnesota','your state is highlighted');
 expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'open list must not cause sideways scrolling');
 expect(await p.locator('#view .facts dd:has-text("Check the offer page")').count()===0,'old wording is gone')}},
{name:'on a computer, hovering opens the state list and moving away closes it',async fn({device}){const p=await device({viewport:{width:1280,height:900}});await p.goHome();
 await seed(p,{state:'MN',ddCap:3000,splits:'3',transfers:true,cash:5000,pace:'2'});await p.click('nav [data-tab="find"]');
 const d=p.locator('#view details.stl').first();await d.scrollIntoViewIfNeeded();
 const before=await d.locator('xpath=ancestor::dl[1]').boundingBox();
 await d.locator('summary').hover();await p.waitForTimeout(150);expect(await d.evaluate(e=>e.open),'hover should open the list');
 const after=await d.locator('xpath=ancestor::dl[1]').boundingBox();expect(Math.abs(after.height-before.height)<1,'the open list should float over the card, not push it down');
 await d.locator('li').first().hover();await p.waitForTimeout(300);expect(await d.evaluate(e=>e.open),'list stays open while the pointer is on it');
 await p.mouse.move(5,5);await p.waitForTimeout(400);expect(!(await d.evaluate(e=>e.open)),'moving away should close it');
 await d.locator('summary').focus();await p.keyboard.press('Enter');expect(await d.evaluate(e=>e.open),'keyboard still opens it');
 await p.keyboard.press('Escape');expect(!(await d.evaluate(e=>e.open)),'Escape closes it')}},
{name:'every card has the status dropdown on top and the bank link below it',async fn({device}){for(const w of [390,1280]){const p=await device({viewport:{width:w,height:900}});await p.goHome();
 await p.click('nav [data-tab="find"]');const rows=await p.locator('#view .foot').evaluateAll(fs=>fs.map(f=>{const s=f.querySelector('select'),a=f.querySelector('a.go');if(!s||!a)return null;
  const r1=s.getBoundingClientRect(),r2=a.getBoundingClientRect();return {below:r2.top>=r1.bottom-1,sameLeft:Math.abs(r1.left-r2.left)<2,full:Math.abs(r1.width-f.getBoundingClientRect().width)<2}}).filter(Boolean));
 expect(rows.length>5,'cards with links should be shown');
 expect(rows.every(r=>r.below&&r.sameLeft&&r.full),`at ${w}px some cards differ: `+JSON.stringify(rows.filter(r=>!(r.below&&r.sameLeft&&r.full)).slice(0,3)))}}},
];
