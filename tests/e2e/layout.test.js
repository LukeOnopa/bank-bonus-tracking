const {expect}=require('./helpers');
const TABS=['find','mine','cal','guide','data'];
module.exports=[
...[[390,'light'],[390,'dark'],[1280,'light'],[1280,'dark']].map(([w,scheme])=>({name:`no sideways scrolling on any tab at ${w}px, ${scheme} mode`,async fn({device}){
 const p=await device({viewport:{width:w,height:844},colorScheme:scheme});await p.goHome();
 expect(await p.isVisible('#acctbtn'),'Sign in button should be visible in the header');
 for(const t of TABS){await p.click(`nav [data-tab="${t}"]`);await p.waitForTimeout(150);
  const over=await p.evaluate(()=>document.documentElement.scrollWidth-innerWidth);expect(over<=0,`${t} tab scrolls sideways by ${over}px`)}}})),
];
