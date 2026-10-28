import { chromium } from "playwright";
import fs from "node:fs";
const base = process.env.BENCH_URL || "http://127.0.0.1:5173";
const browser = await chromium.launch({headless: true,args:["--no-sandbox","--enable-precise-memory-info","--js-flags=--expose-gc"]});
try {
  const page = await browser.newPage({viewport:{width:1280,height:860},deviceScaleFactor:1});
  await page.goto(base,{waitUntil:"networkidle"});
  await page.waitForFunction(() => typeof window.__rmBench?.load === "function");
  const output = {};
  for (const size of [82,302,802]) {
    const samples = [];
    for (let i = 0; i < 3; i++) {
      const mount = await page.evaluate(size => window.__rmBench.load(size),size);
      if (mount.rows !== size) throw new Error("DOM hierarchy count mismatch");
      const refresh = await page.evaluate(() => window.__rmBench.refresh());
      const edit = await page.evaluate(() => window.__rmBench.edit());
      const move = await page.evaluate(() => window.__rmBench.move());
      const heapBytes = await page.evaluate(() => {
        window.gc?.();
        return performance.memory?.usedJSHeapSize ?? null;
      });
      samples.push({ mount_ms:mount.ms, refresh_ms:refresh, edit_ms:edit,move_ms:move,heap_mib:heapBytes/1048576 });
    }
    const result = {};
    for (const key of Object.keys(samples[0])) {
      const sorted = samples.map(s=>s[key]).sort((a,b)=>a-b);
      result[key] = Math.round(sorted[1]*100)/100;
    }
    output[size] = result;
    console.log(size, JSON.stringify(result));
  }
  fs.mkdirSync("data",{recursive:true});
  fs.writeFileSync("data/react-results.json",JSON.stringify(output,null,2));
  const row=page.locator('[data-rowkind="module"]').first();
  await row.locator("input").fill("Real browser edit");
  await row.locator(".apply").click();
  const edited=await row.locator("input").inputValue();
  if (edited!=="Real browser edit") throw Error("Inline browser editing regression");
  console.log("Browser inline editing smoke: PASSED");
} finally { await browser.close(); }
