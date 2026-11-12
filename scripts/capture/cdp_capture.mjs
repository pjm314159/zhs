// CDP 抓包：启动 chrome-win（独立 profile），录下所有 zhihuishu 请求/响应到 JSONL。
//
// 在 Windows 上运行（与 Chrome 同侧，不经过 WSL 的 localhost 转发）：
//   cd C:\Users\ignve\Documents\repos\zhs
//   node scripts\capture\cdp_capture.mjs [输出文件]
//
// 运行期间在弹出的浏览器里正常操作；Ctrl+C 结束录制并关闭浏览器。
// 端口被占用时设置 CDP_PORT。只依赖 Node 22+ 内置的 fetch / WebSocket。
import { spawn, execFileSync } from "node:child_process";
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = resolve(process.argv[2] ?? join(repo, ".capture", `capture-${Date.now()}.jsonl`));
mkdirSync(dirname(out), { recursive: true });

// CHROME_EXE 可换成系统 Google Chrome：chrome-win 是开源 Chromium 快照，不带 H.264/AAC 解码器，放不了知到的视频
const exe = process.env.CHROME_EXE ?? join(repo, "chrome-win", process.platform === "win32" ? "chrome.exe" : "chrome");
const profile = process.env.CHROME_PROFILE ?? join(repo, ".capture", "profile");
mkdirSync(profile, { recursive: true });
const PORT = Number(process.env.CDP_PORT ?? 9555);

// CDP_ATTACH=1：只挂到已在 PORT 上运行的浏览器，不再启动新的
const attachOnly = process.env.CDP_ATTACH === "1";
const chrome = attachOnly ? null : spawn(exe, [
  `--user-data-dir=${profile}`,
  `--remote-debugging-port=${PORT}`,
  "--no-first-run",
  "--no-default-browser-check",
  // 窗口被遮挡/不在前台时 Chromium 会把页面标成 hidden 并暂停媒体加载，抓播放心跳时必须关掉
  "--disable-features=CalculateNativeWinOcclusion",
  "--disable-backgrounding-occluded-windows",
  "--disable-renderer-backgrounding",
  "--disable-background-timer-throttling",
  "--autoplay-policy=no-user-gesture-required",
  "https://onlineweb.zhihuishu.com/",
], { stdio: "ignore" });
if (chrome) chrome.on("error", (e) => { console.error(`[capture] 启动失败: ${e.message}`); process.exit(1); });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const killTree = () => {
  try {
    if (process.platform === "win32") {
      const ps = `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -like '*${profile.replace(/'/g, "''")}*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`;
      execFileSync("powershell.exe", ["-NoProfile", "-Command", ps], { stdio: "ignore" });
    } else if (chrome) {
      chrome.kill();
    }
  } catch {}
};

let version;
for (let i = 0; i < 100 && !version; i++) {
  try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); }
  catch { await sleep(200); }
}
if (!version) { killTree(); throw new Error(`连不上 DevTools 端口 ${PORT}（端口被占用可设 CDP_PORT）`); }
console.log(`[capture] ${version.Browser}  port=${PORT}\n[capture] 输出: ${out}\n[capture] 在浏览器里操作，Ctrl+C 结束`);

const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let nextId = 1;
const pending = new Map();
const send = (method, params = {}, sessionId) => new Promise((res) => {
  const id = nextId++;
  pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});

const reqs = new Map(); // key: sessionId|requestId
const attached = new Set(); // targetId，避免同一页面挂两次导致每条请求录两遍
// 只留接口请求：静态资源（js/css/图片/字体/媒体）不录
const isZhs = (url) => { try { return /(^|\.)zhihuishu\.com$/.test(new URL(url).hostname); } catch { return false; } };
const keep = (url) => isZhs(url)
  && !/\.(js|mjs|map|png|jpe?g|gif|svg|webp|woff2?|ttf|css|ico|mp4|m3u8|ts|html?)(\?|$)/i.test(url);
const write = (rec) => appendFileSync(out, JSON.stringify(rec) + "\n");

ws.addEventListener("message", async (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return; }
  const { method, params, sessionId } = msg;
  if (method === "Target.attachedToTarget") {
    const sid = params.sessionId;
    if (attached.has(params.targetInfo.targetId)) {
      await send("Runtime.runIfWaitingForDebugger", {}, sid);
      return;
    }
    attached.add(params.targetInfo.targetId);
    await send("Network.enable", { maxPostDataSize: 65536 }, sid);
    await send("Runtime.runIfWaitingForDebugger", {}, sid);
    return;
  }
  const key = `${sessionId}|${params?.requestId}`;
  if (method === "Network.requestWillBeSent" && keep(params.request.url)) {
    reqs.set(key, { t: Date.now(), method: params.request.method, url: params.request.url,
      postData: params.request.postData ?? null, type: params.type });
  } else if (method === "Network.responseReceived" && reqs.has(key)) {
    reqs.get(key).status = params.response.status;
  } else if (method === "Network.loadingFinished" && reqs.has(key)) {
    const rec = reqs.get(key); reqs.delete(key);
    const body = await send("Network.getResponseBody", { requestId: params.requestId }, sessionId);
    const r = body.result;
    rec.response = r ? (r.base64Encoded ? "<base64>" : r.body.slice(0, 20000)) : null;
    write(rec);
    console.log(`${new Date(rec.t).toISOString().slice(11, 19)} ${rec.method} ${rec.status} ${rec.url.slice(0, 140)}`);
  } else if (method === "Network.loadingFailed" && reqs.has(key)) {
    const rec = reqs.get(key); reqs.delete(key); rec.failed = params.errorText; write(rec);
  }
});

await send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: true, flatten: true,
  filter: [{ type: "page" }, { type: "iframe" }, { type: "worker" }, { type: "service_worker" }] });
await send("Target.setDiscoverTargets", { discover: true });
const targets = await send("Target.getTargets");
for (const t of targets.result.targetInfos) {
  if (t.type === "page" && !attached.has(t.targetId)) {
    await send("Target.attachToTarget", { targetId: t.targetId, flatten: true });
  }
}

const stop = () => { if (!attachOnly) killTree(); process.exit(0); };
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
// Chromium 的启动进程会在交接后退出，不能据此判断浏览器关了；以 CDP 连接断开为准
ws.addEventListener("close", () => { console.log("[capture] 浏览器已关闭"); process.exit(0); });
