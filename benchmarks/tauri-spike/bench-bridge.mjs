import { spawn } from "node:child_process";
import { performance } from "node:perf_hooks";
import fs from "node:fs";
import readline from "node:readline";
import path from "node:path";

const python = process.env.BENCH_PYTHON || "python3";
const child = spawn(python, ["bridge.py"], { cwd:process.cwd(),
 env:{...process.env,PYTHONPATH:path.resolve("../../src")},stdio:["pipe","pipe","inherit"]});
const queue = new Map();
let counter = 0;
const lines = readline.createInterface({input:child.stdout});
lines.on("line",line=>{const reply=JSON.parse(line); const p=queue.get(reply.id);if(p){queue.delete(reply.id);p.resolve(reply);}});
function send(command) {
 const id=++counter;
 return new Promise((resolve,reject)=>{queue.set(id,{resolve,reject});
 child.stdin.write(JSON.stringify({id,...command})+"\n");});
}
const med = x => [...x].sort((a,b)=>a-b)[Math.floor(x.length/2)];
const p95 = x => [...x].sort((a,b)=>a-b)[Math.min(x.length-1,Math.ceil(x.length*.95)-1)];
async function timed(command) {
 const start=performance.now();
 const response=await send(command);
 const ms=performance.now()-start;
 if(!response.ok)throw Error(JSON.stringify(response));
 return {ms,response:response.result};
}
try {
 const init=(await timed({action:"hello"})).response;
 let rev=init.revision;
 const ping=[],rename=[];
 for(let i=0;i<50;i++)ping.push((await timed({action:"hello"})).ms);
 for(let i=0;i<30;i++) {
   const result=await timed({action:"rename",target:init.firstModule,text:"Synthetic title "+i,
     expectedRevision:rev,generation:init.generation});
   rev=result.response.revision;rename.push(result.ms);
 }
 const change=await timed({action:"move",source:init.firstModule,target:init.secondModule,
   position:"after",expectedRevision:rev,generation:init.generation});
 rev=change.response.revision;
 if (change.response.firstModule!==init.secondModule) throw Error("Move did not reorder canonical tree");
 const stale=await send({action:"rename",target:init.firstModule,text:"Bad stale write",
   expectedRevision:rev-1,generation:init.generation});
 if(stale.ok)throw Error("Stale revision unexpectedly accepted");
 const undone=await timed({action:"undo",expectedRevision:rev,generation:init.generation});
 if(undone.response.firstModule!==init.firstModule)throw Error("Canonical undo failed");
 const output={n:init.nodes,read_median_ms:+med(ping).toFixed(3),read_p95_ms:+p95(ping).toFixed(3),
   command_median_ms:+med(rename).toFixed(3),command_p95_ms:+p95(rename).toFixed(3),
   move_ms:+change.ms.toFixed(3),undo_ms:+undone.ms.toFixed(3),
   stale_rejected:true,undo_verified:true,commands:30};
 console.log(JSON.stringify(output,null,2));
 fs.mkdirSync("data",{recursive:true});
 fs.writeFileSync("data/bridge-results.json",JSON.stringify(output,null,2));
}finally{child.stdin.end();child.kill();}
