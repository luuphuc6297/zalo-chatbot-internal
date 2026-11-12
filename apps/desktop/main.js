// Minimal Electron shell for the staff console (apps/console).
//
// What it loads:
//   THOMHOUSE_CONSOLE_URL set (pnpm dev): that URL, e.g. http://localhost:5173 (run `pnpm dev:console` first).
//   otherwise: ../console/dist/index.html if built (`pnpm -C apps/console build`), else http://localhost:5173.
//
// Security: contextIsolation on, nodeIntegration off, sandbox on, a preload exposing only getConfig/setConfig,
// IPC accepted only from the console page, navigation and new windows blocked (http(s) links open in the
// default browser), permission requests denied, CSP header for the dev URL (the built page carries a CSP meta).
//
// Config: server URL, staff id and staff token in <userData>/console-config.json; the token is encrypted with
// safeStorage (macOS Keychain). If encryption is unavailable the token is not stored.
//
// CORS: the Worker sends no CORS headers yet. Observed with Electron 45: the built page (file://) can call the
// Worker without CORS (smoke run with and without the shim below both got 200). The shim matters when the dev
// page (http://localhost:5173) is given an absolute server URL: for requests from this window to the configured
// server origin only, it answers the preflight with 204 and adds Access-Control-Allow-* headers. With baseUrl ''
// the dev page calls the Vite proxy and needs no CORS at all.
//
// THOMHOUSE_DESKTOP_SMOKE=1: open the window hidden, check the console mounted and the bridge exists, print a
// JSON line and exit (0 ok, 1 failed). THOMHOUSE_DESKTOP_SMOKE_FETCH=<url> also fetches that URL from the page
// with an Authorization header. THOMHOUSE_DESKTOP_USER_DATA overrides the userData dir (tests).
'use strict';

const path = require('node:path');
const fs = require('node:fs');
const { app, BrowserWindow, ipcMain, safeStorage, session, shell } = require('electron');

const DEV_URL = process.env.THOMHOUSE_CONSOLE_URL;
const DIST_INDEX = path.join(__dirname, '..', 'console', 'dist', 'index.html');
const SMOKE = process.env.THOMHOUSE_DESKTOP_SMOKE === '1';
const DEFAULT_API = 'http://127.0.0.1:8787';

if (process.env.THOMHOUSE_DESKTOP_USER_DATA) app.setPath('userData', process.env.THOMHOUSE_DESKTOP_USER_DATA);

function consoleTarget() {
  if (DEV_URL) return { kind: 'url', value: DEV_URL };
  if (fs.existsSync(DIST_INDEX)) return { kind: 'file', value: DIST_INDEX };
  return { kind: 'url', value: 'http://localhost:5173' };
}

const target = consoleTarget();
const allowedOrigin = target.kind === 'url' ? new URL(target.value).origin : 'file://';

function isConsoleUrl(url) {
  if (typeof url !== 'string') return false;
  return allowedOrigin === 'file://' ? url.startsWith('file://') : url === allowedOrigin || url.startsWith(allowedOrigin + '/');
}

// ---------------------------------------------------------------- config storage

function configPath() {
  return path.join(app.getPath('userData'), 'console-config.json');
}

function readStored() {
  try {
    return JSON.parse(fs.readFileSync(configPath(), 'utf8'));
  } catch {
    return {};
  }
}

function getConfig() {
  const s = readStored();
  let staffToken = '';
  if (typeof s.staffTokenEnc === 'string' && s.staffTokenEnc && safeStorage.isEncryptionAvailable()) {
    try {
      staffToken = safeStorage.decryptString(Buffer.from(s.staffTokenEnc, 'base64'));
    } catch {
      staffToken = ''; // keychain item changed or file copied from another machine: ask again
    }
  }
  return {
    baseUrl: typeof s.baseUrl === 'string' ? s.baseUrl : DEFAULT_API,
    staffId: typeof s.staffId === 'string' ? s.staffId : 'staff',
    staffToken,
  };
}

function validBaseUrl(u) {
  if (u === '') return true;
  try {
    const p = new URL(u);
    return (p.protocol === 'https:' || p.protocol === 'http:') && !p.username && !p.password;
  } catch {
    return false;
  }
}

function setConfig(cfg) {
  if (!cfg || typeof cfg !== 'object') return { ok: false, error: 'Cấu hình không hợp lệ' };
  const baseUrl = typeof cfg.baseUrl === 'string' ? cfg.baseUrl.trim().replace(/\/+$/, '') : '';
  const staffId = typeof cfg.staffId === 'string' ? cfg.staffId.trim().slice(0, 64) : 'staff';
  const staffToken = typeof cfg.staffToken === 'string' ? cfg.staffToken.trim() : '';
  if (!validBaseUrl(baseUrl)) return { ok: false, error: 'Địa chỉ máy chủ phải bắt đầu bằng http:// hoặc https://' };
  if (allowedOrigin === 'file://' && baseUrl === '') return { ok: false, error: 'Bản desktop cần địa chỉ máy chủ đầy đủ' };
  if (staffToken.length > 4096) return { ok: false, error: 'Staff token quá dài' };
  if (staffToken && !safeStorage.isEncryptionAvailable()) {
    return { ok: false, error: 'Máy này không mã hóa được token (safeStorage không dùng được); token không được lưu' };
  }
  const out = {
    baseUrl,
    staffId: staffId || 'staff',
    staffTokenEnc: staffToken ? safeStorage.encryptString(staffToken).toString('base64') : '',
  };
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  const tmp = configPath() + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(out), { mode: 0o600 });
  fs.renameSync(tmp, configPath());
  return { ok: true };
}

function fromConsole(event) {
  const url = event.senderFrame && event.senderFrame.url;
  return isConsoleUrl(url);
}

ipcMain.handle('thomhouse:config:get', (event) => {
  if (!fromConsole(event)) throw new Error('forbidden');
  return getConfig();
});
ipcMain.handle('thomhouse:config:set', (event, cfg) => {
  if (!fromConsole(event)) throw new Error('forbidden');
  return setConfig(cfg);
});

// ---------------------------------------------------------------- CSP and CORS

const DEV_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'", // Vite's React refresh preamble is an inline script (dev only)
  "style-src 'self' 'unsafe-inline'", // Vite injects CSS with <style> in dev
  "img-src 'self' data:",
  `connect-src 'self' ws://${DEV_URL ? new URL(DEV_URL).host : 'localhost:5173'} http://127.0.0.1:8787 http://localhost:8787 https:`,
  "object-src 'none'",
  "base-uri 'none'",
].join('; ');

function apiOrigin() {
  try {
    const u = getConfig().baseUrl;
    return u ? new URL(u).origin : null;
  } catch {
    return null;
  }
}

function setHeader(headers, name, value) {
  for (const k of Object.keys(headers)) if (k.toLowerCase() === name.toLowerCase()) delete headers[k];
  headers[name] = [value];
}

function installSessionPolicy(ses, webContentsId) {
  ses.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  ses.webRequest.onHeadersReceived((details, cb) => {
    const headers = { ...(details.responseHeaders || {}) };
    if (details.resourceType === 'mainFrame' && target.kind === 'url' && isConsoleUrl(details.url)) {
      setHeader(headers, 'Content-Security-Policy', DEV_CSP);
      return cb({ responseHeaders: headers });
    }
    const origin = apiOrigin();
    let reqOrigin = null;
    try {
      reqOrigin = new URL(details.url).origin;
    } catch {
      /* ignore */
    }
    if (origin && reqOrigin === origin && details.webContentsId === webContentsId && origin !== allowedOrigin) {
      setHeader(headers, 'Access-Control-Allow-Origin', '*');
      // PATCH: contact profile edits (PATCH /staff/profiles/:zalo_user_id, docs/contracts.md section 13)
      setHeader(headers, 'Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, OPTIONS');
      setHeader(headers, 'Access-Control-Allow-Headers', 'authorization, content-type, x-staff-id');
      setHeader(headers, 'Access-Control-Max-Age', '600');
      if (details.method === 'OPTIONS') return cb({ responseHeaders: headers, statusLine: 'HTTP/1.1 204 No Content' });
    }
    cb({ responseHeaders: headers });
  });
}

// ---------------------------------------------------------------- window

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    title: 'thom house',
    show: !SMOKE,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      webviewTag: false,
      spellcheck: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  installSessionPolicy(win.webContents.session, win.webContents.id);

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!isConsoleUrl(url)) event.preventDefault();
  });
  win.webContents.on('will-attach-webview', (event) => event.preventDefault());

  if (SMOKE) runSmoke(win);

  if (target.kind === 'url') win.loadURL(target.value);
  else win.loadFile(target.value);
  return win;
}

function runSmoke(win) {
  const problems = [];
  win.webContents.on('console-message', (event) => {
    const level = event.level;
    const message = event.message;
    if (level === 'error' || level === 3 || /Content Security Policy/i.test(String(message))) problems.push(String(message));
  });
  win.webContents.on('did-fail-load', (_e, code, desc) => {
    problems.push(`did-fail-load ${code} ${desc}`);
  });
  win.webContents.once('did-finish-load', async () => {
    await new Promise((r) => setTimeout(r, 1500));
    let page = {};
    try {
      page = await win.webContents.executeJavaScript(
        `({ mounted: document.getElementById('root')?.children.length > 0,
            bridge: typeof window.thomhouse?.getConfig === 'function' && typeof window.thomhouse?.setConfig === 'function',
            nodeLeak: typeof window.require !== 'undefined' || typeof window.process !== 'undefined',
            csp: document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.content ?? null,
            title: document.title })`,
      );
      if (process.env.THOMHOUSE_DESKTOP_SMOKE_FETCH) {
        // Cross-origin call with an Authorization header from the console page (exercises the CORS shim).
        page.fetch = await win.webContents.executeJavaScript(
          `fetch(${JSON.stringify(process.env.THOMHOUSE_DESKTOP_SMOKE_FETCH)}, { headers: { authorization: 'Bearer smoke' } })
             .then(async (r) => ({ status: r.status, body: await r.text() }))
             .catch((e) => ({ error: String(e) }))`,
        );
      }
    } catch (e) {
      problems.push(`executeJavaScript: ${e.message}`);
    }
    const ok = page.mounted === true && page.bridge === true && page.nodeLeak === false && (!page.fetch || page.fetch.status === 200);
    process.stdout.write(JSON.stringify({ smoke: ok ? 'ok' : 'failed', target: target.kind, ...page, problems }) + '\n');
    app.exit(ok ? 0 : 1);
  });
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('web-contents-created', (_e, contents) => {
  contents.on('will-navigate', (event, url) => {
    if (!isConsoleUrl(url)) event.preventDefault();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin' || SMOKE) app.quit();
});
