// The Refresh offers button (Supabase Edge Function refresh-offers), against the in-memory stand-in.
const {expect}=require('./helpers');
const fs=require('fs'),path=require('path');
const curated=JSON.parse(fs.readFileSync(path.join(__dirname,'../../data/curated.json'),'utf8'));
const snapshot=(extra=[],generated='2026-11-27T12:00:00Z')=>({generated,sources:[{name:'Doctor of Credit',ok:true}],offers:[...curated,...extra]});
const NEW={id:'auto-brandnew',b:'Brand New Bank',a:'Checking',t:'bank',amt:777,dd:500,win:60,st:['MN'],stSrc:'article',auto:1,quick:1,seen:'2026-11-27',req:'$500 in direct deposits within 60 days.'};
async function signIn(p){await p.click('#acctbtn');await p.click('[data-act=acct-mode][data-m=up]');await p.fill('#acctf [name=email]','r@test.com');
 await p.fill('#acctf [name=pw]','password123');await p.click('#acctf button[type=submit]');await p.waitForSelector('#acctbtn:has-text("My account")')}
module.exports=[
{name:'signed-out visitors are asked to sign in to refresh',async fn({device,sb}){sb.siteData=snapshot();const p=await device();await p.goHome('#find');
 await p.waitForSelector('#stats [data-act="acct"]:has-text("Sign in to refresh")');
 expect(await p.locator('[data-act="refresh-offers"]').count()===0,'no refresh button when signed out')}},
{name:'Refresh offers updates the list in place and says what changed',async fn({device,sb}){sb.siteData=snapshot();
 sb.refresh=()=>({data:snapshot([NEW],'2026-11-27T13:00:00Z'),body:{updated:true,generated:'2026-11-27T13:00:00Z',added:['Brand New Bank'],changed:0}});
 const p=await device();await p.goHome();await signIn(p);await p.click('nav [data-tab="find"]');
 expect(!(await p.content()).includes('Brand New Bank'),'the new offer is not there before refreshing');
 await p.click('[data-act="refresh-offers"]');await p.waitForSelector('.rfmsg:has-text("Offers updated: 1 new offer")');
 await p.fill('#view input[type=search]','Brand New');await p.waitForTimeout(300);
 const card=await p.locator('#view article:has-text("Brand New Bank")').first().innerText();
 expect(card.includes('Just added from the bonus sites'),'a quick-added offer says its details come at the next daily update')}},
{name:'a second refresh within 5 minutes says when it can run again',async fn({device,sb}){sb.siteData=snapshot();
 sb.refresh=()=>({status:429,body:{error:'busy',nextAllowedAt:'2026-11-27T13:05:00Z'}});
 const p=await device();await p.goHome();await signIn(p);await p.click('nav [data-tab="find"]');
 await p.click('[data-act="refresh-offers"]');await p.waitForSelector('.rfmsg:has-text("You can refresh again after")')}},
{name:'the newer of the daily list and the quick refresh is shown',async fn({device,sb}){sb.siteData=snapshot([NEW],'2099-01-01T00:00:00Z');
 const p=await device();await p.goHome('#find');await p.fill('#view input[type=search]','Brand New');await p.waitForTimeout(300);
 expect(await p.locator('#view article:has-text("Brand New Bank")').count()===1,'quick-refresh offers are shown when they are newer')}},
];
