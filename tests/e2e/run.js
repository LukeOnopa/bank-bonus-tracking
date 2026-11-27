// Browser tests for the app. Run: node tests/e2e/run.js [name-filter]
// Each test gets a fresh browser and a fresh stand-in for the Supabase account service.
const {chromium}=require('playwright');
const http=require('http'),fs=require('fs'),path=require('path');
const {mockSupabase}=require('./mock-supabase');
const ROOT=path.resolve(__dirname,'../..');
const SB_URL=(fs.readFileSync(path.join(ROOT,'index.html'),'utf8').match(/const SB_URL="([^"]*)"/)||[])[1];
const TYPES={'.html':'text/html','.json':'application/json','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'};

function serve(){return new Promise(r=>{const s=http.createServer((q,res)=>{
  let f=decodeURIComponent(new URL(q.url,'http://x').pathname);if(f.endsWith('/'))f+='index.html';
  const fp=path.join(ROOT,f);
  if(!fp.startsWith(ROOT)||!fs.existsSync(fp)||fs.statSync(fp).isDirectory()){res.writeHead(404);res.end();return}
  res.writeHead(200,{'Content-Type':TYPES[path.extname(fp)]||'application/octet-stream'});fs.createReadStream(fp).pipe(res)})
 .listen(0,'127.0.0.1',()=>r(s))})}

// errors that are expected when running locally (data/offers.json is built by the hourly job, not committed)
const IGNORE=/offers\.json|Failed to load resource|account error|sync failed/;

(async()=>{
 const filter=process.argv[2]||'';
 const files=fs.readdirSync(__dirname).filter(f=>f.endsWith('.test.js')).sort();
 const tests=files.flatMap(f=>require('./'+f).map(t=>({...t,file:f}))).filter(t=>(t.file+' '+t.name).includes(filter));
 const server=await serve(),URL_=`http://127.0.0.1:${server.address().port}/`;
 const browser=await chromium.launch();let failed=0;
 for(const t of tests){
  const sb=mockSupabase(),ctxs=[],pages=[];
  const device=async(opts={})=>{const ctx=await browser.newContext({viewport:{width:1280,height:900},...opts});ctxs.push(ctx);
   if(SB_URL)await ctx.route(SB_URL+'/**',route=>sb.handle(route));
   const page=await ctx.newPage();page.errors=[];pages.push(page);
   page.on('pageerror',e=>page.errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&!IGNORE.test(m.text()))page.errors.push(m.text())});
   page.goHome=async(hash='')=>{await page.goto(URL_+hash);await page.waitForFunction(()=>document.querySelector('#view')?.children.length>0);await page.waitForTimeout(150)};
   return page};
  const start=Date.now();
  try{await t.fn({device,sb,url:URL_,SB_URL});
   const errs=pages.flatMap(p=>p.errors);if(errs.length&&!t.allowErrors)throw new Error('Page errors: '+errs.join(' | '));
   console.log(`PASS ${t.file} › ${t.name} (${Date.now()-start} ms)`)}
  catch(e){failed++;console.log(`FAIL ${t.file} › ${t.name}\n     ${String(e&&e.message||e).split('\n').join('\n     ')}`)}
  finally{for(const c of ctxs)await c.close()}}
 await browser.close();server.close();
 console.log(`\n${tests.length-failed} passed, ${failed} failed`);process.exit(failed?1:0)})();
