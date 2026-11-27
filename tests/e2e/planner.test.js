// The plan must never ask for more than the user said they can handle.
const {expect,seed}=require('./helpers');
const day=(d,n)=>{const x=new Date(d+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10)};
function check(plan,{ddCap,splits,pace},extra=[]){const all=[...extra,...plan];
 for(const a of plan){const live=all.filter(b=>b.on<=a.on&&b.end>a.on);
  const used=live.reduce((s,b)=>s+b.m,0);expect(used<=ddCap,`paycheck room exceeded on ${a.on}: $${used} of $${ddCap}`);
  const dd=live.filter(b=>b.dd&&!b.flex).length;expect(dd<=+splits,`paycheck splits exceeded on ${a.on}: ${dd} of ${splits}`);
  const recent=plan.filter(b=>b.on>day(a.on,-30)&&b.on<=a.on).length;expect(recent<=+pace,`more than ${pace} applications in the 30 days to ${a.on}: ${recent}`)}
 const banks=plan.map(x=>x.o.b);expect(new Set(banks).size===banks.length,'the same bank is planned twice: '+banks)}
const PROFILES=[
 {state:'MN',ddCap:3000,splits:'3',transfers:true,cash:5000,pace:'2'},
 {state:'MN',ddCap:1500,splits:'1',transfers:false,cash:1000,pace:'1'},
 {state:'CA',ddCap:8000,splits:'5',transfers:true,cash:20000,pace:'3'},
 {state:'TX',ddCap:500,splits:'2',transfers:false,cash:500,pace:'2'},
];
module.exports=[
...PROFILES.map(P=>({name:`plan stays within limits: ${P.state}, $${P.ddCap}/mo, ${P.splits} split(s), ${P.pace}/month`,async fn({device}){
 const p=await device();await p.goHome();await seed(p,P);
 const plan=await p.evaluate(()=>window.__plan());check(plan,P);
 const st=plan.map(x=>x.o.st);
 expect(st.every(s=>s==='ALL'||(Array.isArray(s)&&s.includes(P.state))),'plan includes an offer not available in '+P.state)}})),
{name:'an open account uses up paycheck room and its bank is not planned again',async fn({device}){const P=PROFILES[0];const p=await device();await p.goHome();await seed(p,P);
 const first=(await p.evaluate(()=>window.__plan())).find(x=>x.m>0&&!x.flex);expect(first,'need a plan item that uses a paycheck');
 const today=new Date().toISOString().slice(0,10);
 await seed(p,P,{[first.o.id]:{status:'open',opened:today,u:1}});
 const plan=await p.evaluate(()=>window.__plan());
 check(plan,P,[{on:today,end:day(today,first.o.win||90),m:first.m,dd:true,flex:false,o:first.o}]);
 expect(!plan.some(x=>x.o.b===first.o.b),'bank with an open account was planned again')}},
];
