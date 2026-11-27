// In-memory stand-in for Supabase auth and the user_data table, served through Playwright request routing.
// It follows the real API's shapes closely enough for the app: tokens, refresh, row-level security by user.
function mockSupabase({confirmEmail=false}={}){
 const users={},rows={},tokens={},log=[];let n=0,deny=false,offline=false,siteData=null,refresh=null;
 const session=u=>{const at='at'+(++n),rt='rt'+n;tokens[at]=u;tokens[rt]=u;return{access_token:at,refresh_token:rt,expires_in:3600,user:{id:u.id,email:u.email}}};
 async function handle(route){const q=route.request(),u=new URL(q.url()),method=q.method();
  if(offline)return route.abort('internetdisconnected');
  const body=q.postData()?JSON.parse(q.postData()):{},me=tokens[(q.headers().authorization||'').replace('Bearer ','')];
  const send=(status,json)=>route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:json==null?'':JSON.stringify(json)});
  if(method==='OPTIONS')return route.fulfill({status:200,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  log.push(method+' '+u.pathname+u.search);
  if(!/^sb_publishable_/.test(q.headers().apikey||''))return send(401,{message:'No API key found in request'});
  const p=u.pathname;
  if(p==='/auth/v1/signup'){if(users[body.email])return confirmEmail?send(200,{id:'fake'}):send(422,{error_code:'user_already_exists',msg:'User already registered'});
   const x=users[body.email]={id:'u'+(++n),email:body.email,pw:body.password,ok:!confirmEmail};return send(200,confirmEmail?{id:x.id,email:x.email}:session(x))}
  if(p==='/auth/v1/token'){if(u.searchParams.get('grant_type')==='password'){const x=users[body.email];
    if(!x||x.pw!==body.password)return send(400,{error_code:'invalid_credentials',msg:'Invalid login credentials'});
    if(!x.ok)return send(400,{error_code:'email_not_confirmed',msg:'Email not confirmed'});return send(200,session(x))}
   const x=tokens[body.refresh_token];if(!x)return send(400,{error_code:'refresh_token_not_found',msg:'Invalid Refresh Token'});delete tokens[body.refresh_token];return send(200,session(x))}
  if(p==='/auth/v1/recover')return send(200,{});
  if(p==='/auth/v1/logout')return send(204);
  if(p==='/rest/v1/site_data')return send(200,siteData?[{data:siteData}]:[]);   // public read, like the real table
  if(!me)return send(401,{code:'PGRST301',message:'JWT expired'});
  if(p==='/auth/v1/user'){if(method==='PUT'){if(body.password===me.pw)return send(422,{error_code:'same_password',msg:'New password should be different from the old password.'});me.pw=body.password}return send(200,{id:me.id,email:me.email})}
  if(p==='/functions/v1/refresh-offers'){if(!refresh)return send(500,{error:'server',message:'not set up in test'});
   const r=refresh();if(r.data)siteData=r.data;return send(r.status||200,r.body)}
  if(p==='/rest/v1/user_data'){if(deny)return send(403,{code:'42501',message:'permission denied for table user_data'});
   if(method==='GET'){const id=(u.searchParams.get('user_id')||'').replace('eq.','');return send(200,id===me.id&&rows[id]?[{state:rows[id].state}]:[])}
   if(body.user_id!==me.id)return send(403,{code:'42501',message:'new row violates row-level security policy'});rows[me.id]=body;return send(201)}
  return send(404,{message:'not found'})}
 return{handle,log,users,
  row:email=>users[email]&&rows[users[email].id]?.state,
  expireTokens(){for(const k in tokens)if(k.startsWith('at'))delete tokens[k]},
  session:email=>session(users[email]),
  set deny(v){deny=v},set offline(v){offline=v},set siteData(v){siteData=v},set refresh(f){refresh=f}}}
module.exports={mockSupabase};
