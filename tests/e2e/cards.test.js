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
];
