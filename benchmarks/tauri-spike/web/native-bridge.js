import { Command } from "@tauri-apps/plugin-shell";

/** A narrow, long-lived JSONL transport. The Python gateway remains authoritative. */
export async function startNativeBridge() {
  const command = Command.sidecar("binaries/reportmaker-bench-bridge");
  let child;
  let next = 0;
  const inflight = new Map();
  let buffer = "";
  command.stdout.on("data", chunk => {
    buffer += String(chunk);
    let end;
    while ((end = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0,end).trim();
      buffer = buffer.slice(end+1);
      if (!line) continue;
      try {
        const reply = JSON.parse(line);
        const pending = inflight.get(reply.id);
        if (pending) {
          inflight.delete(reply.id);
          if (reply.ok) pending.resolve(reply.result);
          else pending.reject(new Error(reply.error));
        }
      } catch (error) {
        for (const request of inflight.values()) request.reject(error);
        inflight.clear();
      }
    }
  });
  command.on("close", () => {
    for (const request of inflight.values()) request.reject(Error("Bridge closed"));
    inflight.clear();
  });
  child = await command.spawn();
  return {
    request(command) {
      const id = ++next;
      return new Promise((resolve,reject) => {
        inflight.set(id,{resolve,reject});
        child.write(JSON.stringify({id,...command})+"\n").catch(error => {
          inflight.delete(id); reject(error);
        });
      });
    },
    close() { return child.kill(); }
  };
}
