// Free accounts, against an in-memory stand-in for Supabase (see mock-supabase.js).
const {expect,state}=require('./helpers');
async function signUp(p,email,pw='password123'){await p.click('#acctbtn');await p.click('[data-act=acct-mode][data-m=up]');
 await p.fill('#acctf [name=email]',email);await p.fill('#acctf [name=pw]',pw);await p.click('#acctf button[type=submit]');
 await p.waitForSelector('#acctbtn:has-text("My account")',{timeout:5000})}
async function signIn(p,email,pw='password123'){await p.click('#acctbtn');await p.fill('#acctf [name=email]',email);await p.fill('#acctf [name=pw]',pw);await p.click('#acctf button[type=submit]')}
async function addOffer(p,bank,amt){await p.click('nav [data-tab="data"]');await p.fill('#add [name=b]',bank);await p.fill('#add [name=amt]',String(amt));await p.click('#add button[type=submit]')}
const banks=s=>(s?.custom||[]).map(c=>c.b);
const settle=p=>p.waitForTimeout(1200); // saves are batched for 0.6 s, then uploaded
module.exports=[
{name:'sign-up checks the email and password',async fn({device}){const p=await device();await p.goHome();
 await p.click('#acctbtn');await p.click('[data-act=acct-mode][data-m=up]');
 await p.fill('#acctf [name=email]','bad');await p.fill('#acctf [name=pw]','password123');await p.click('#acctf button[type=submit]');
 expect(/valid email/.test(await p.textContent('.aerr')),'bad email should be rejected');
 await p.fill('#acctf [name=email]','a@test.com');await p.fill('#acctf [name=pw]','short');await p.click('#acctf button[type=submit]');
 expect(/8 characters/.test(await p.textContent('.aerr')),'short password should be rejected')}},
{name:'data in the browser is added to a new account',async fn({device,sb}){const p=await device();await p.goHome();
 await addOffer(p,'Local CU',150);await signUp(p,'a@test.com');await settle(p);
 expect(banks(sb.row('a@test.com')).includes('Local CU'),'existing data should be uploaded');
 expect((await p.textContent('#sync')).startsWith('Saved to your account'),'sync note should say saved')}},
{name:'a second device gets the data, and changes flow both ways',async fn({device,sb}){
 const A=await device();await A.goHome();await addOffer(A,'Local CU',150);await signUp(A,'a@test.com');await settle(A);
 const B=await device();await B.goHome();await signIn(B,'a@test.com','wrong-password');await B.waitForSelector('.aerr');
 expect(/don't match/.test(await B.textContent('.aerr')),'wrong password message');
 await B.fill('#acctf [name=pw]','password123');await B.click('#acctf button[type=submit]');await settle(B);
 expect(banks(await state(B)).includes('Local CU'),'device B should get the data');
 await addOffer(B,'Second Bank',300);await settle(B);
 await A.evaluate(()=>{Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});document.dispatchEvent(new Event('visibilitychange'))});await settle(A);
 expect(banks(await state(A)).includes('Second Bank'),'device A should pull the change when the user comes back to the tab')}},
{name:'an out-of-date device merges instead of overwriting, and deletes stay deleted',async fn({device,sb}){
 const A=await device();await A.goHome();await addOffer(A,'Local CU',150);await signUp(A,'a@test.com');await settle(A);
 const B=await device();await B.goHome();await signIn(B,'a@test.com');await settle(B);
 await A.click('nav [data-tab="data"]');await A.click('[data-act=del]');await settle(A);
 await addOffer(B,'Third Bank',200);await settle(B);
 const cloud=banks(sb.row('a@test.com'));
 expect(cloud.includes('Third Bank')&&!cloud.includes('Local CU'),'cloud should have the new offer and not the deleted one: '+cloud)}},
{name:'an expired sign-in is refreshed without bothering the user',async fn({device,sb}){const p=await device();await p.goHome();await signUp(p,'a@test.com');await settle(p);
 sb.expireTokens();await addOffer(p,'Fourth',100);await settle(p);
 expect(banks(sb.row('a@test.com')).includes('Fourth'),'change should save after refreshing');
 await p.reload();await p.waitForSelector('#acctbtn:has-text("My account")')}},
{name:'password change rejects the same password and accepts a new one',async fn({device}){const p=await device();await p.goHome();await signUp(p,'a@test.com');
 await p.click('#acctbtn');await p.click('[data-act=acct-pw]');await p.fill('#acctf [name=pw]','password123');await p.click('#acctf button[type=submit]');await p.waitForSelector('.aerr');
 expect(/different/.test(await p.textContent('.aerr')),'same password should be rejected');
 await p.fill('#acctf [name=pw]','newpassword9');await p.click('#acctf button[type=submit]');await p.waitForSelector('.aok');
 expect(/Password updated/.test(await p.textContent('.aok')),'password should change')}},
{name:'offline: changes wait in the browser, and sign-out saves them first',async fn({device,sb}){const p=await device();await p.goHome();await signUp(p,'a@test.com');await settle(p);
 sb.offline=true;await addOffer(p,'Offline Bank',50);await settle(p);
 expect((await p.textContent('#sync')).startsWith("Couldn't reach"),'should warn that it could not reach the account');
 await p.click('[data-act=acct-out]');await p.waitForSelector('.aerr');expect(/still signed in/.test(await p.textContent('.aerr')),'sign-out should wait');
 sb.offline=false;await p.click('[data-act=acct-out]');await p.waitForSelector('#acctbtn:has-text("Sign in")',{timeout:8000});
 expect(banks(sb.row('a@test.com')).includes('Offline Bank'),'offline change should be saved before signing out');
 expect(!(await state(p)),'browser copy should be cleared after sign-out');expect(/Signed out/.test(await p.textContent('#toast')),'signed-out message')}},
{name:'server refusing saves: clear message and Sign out anyway keeps the data',async fn({device,sb}){const p=await device();await p.goHome();await signUp(p,'a@test.com');await settle(p);
 sb.deny=true;await addOffer(p,'Keep Me',99);await settle(p);
 expect(/problem on our side/.test(await p.textContent('#sync')),'should not blame the connection');
 await p.click('[data-act=acct-out]');await p.waitForSelector('[data-act=acct-force]');await p.click('[data-act=acct-force]');
 await p.waitForSelector('#acctbtn:has-text("Sign in")',{timeout:8000});expect(banks(await state(p)).includes('Keep Me'),'unsaved data should stay in the browser')}},
{name:'password-reset link opens the new-password form',async fn({device,sb,url}){const p0=await device();await p0.goHome();await signUp(p0,'a@test.com');
 const t=sb.session('a@test.com');const p=await device();await p.goHome(`#access_token=${t.access_token}&refresh_token=${t.refresh_token}&expires_in=3600&type=recovery`);
 await p.waitForSelector('#acctf[data-mode=reset]');expect(!p.url().includes('access_token'),'token should be removed from the address bar');
 await p.fill('#acctf [name=pw]','resetpass99');await p.click('#acctf button[type=submit]');await p.waitForSelector('#acctbtn:has-text("My account")')}},
{name:'expired email link shows a clear message',async fn({device}){const p=await device();
 await p.goHome('#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired');
 expect(/expired/.test(await p.textContent('.aerr')),'expired link message')}},
];
