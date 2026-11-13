const { app, BrowserWindow, shell } = require("electron");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");
const { stopProxy } = require("./proxy_shutdown.cjs");

const ROOT = path.resolve(__dirname, "..");
app.setPath("userData", path.resolve(ROOT, "..", ".runtime", "profile"));
const HAS_LOCK = app.requestSingleInstanceLock();
if (!HAS_LOCK) app.quit();
app.on("second-instance", () => {
  if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); }
});
const FLASK_PORT = Number(process.env.PORT || 5500);
const FLASK_URL = `http://127.0.0.1:${FLASK_PORT}`;
const VITE_URL = process.env.VITE_URL || "http://127.0.0.1:5173";
const IS_DEV = process.argv.includes("--dev") || process.env.NAW_DEV === "1";

let mainWindow = null;
let flaskProcess = null;
let shuttingDown = false;
let cleanupStarted = false;
let cleanupFinished = false;

function findPython() {
  if (process.env.PYTHON) return process.env.PYTHON;
  return process.platform === "win32" ? "python" : "python3";
}

function isFlaskUp() {
  return new Promise((resolve) => {
    const req = http.get(`${FLASK_URL}/api/health`, (res) => {
      let body = "";
      res.on("data", (data) => { body += data; });
      res.on("end", () => {
        try { resolve(res.statusCode === 200 && path.resolve(JSON.parse(body).root) === ROOT); }
        catch { resolve(false); }
      });
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1200, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function startFlask() {
  if (flaskProcess) return;
  if (await isFlaskUp()) {
    console.log(`[flask] already running on ${FLASK_URL}`);
    return;
  }
  const py = findPython();
  flaskProcess = spawn(py, ["app.py"], {
    cwd: ROOT,
    env: { ...process.env, PORT: String(FLASK_PORT), PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  flaskProcess.stdout.on("data", (buf) => {
    const line = String(buf).trim();
    if (line) console.log(`[flask] ${line}`);
  });
  flaskProcess.stderr.on("data", (buf) => {
    const line = String(buf).trim();
    if (line) console.error(`[flask] ${line}`);
  });
  flaskProcess.on("exit", (code) => {
    console.log(`[flask] exited code=${code}`);
    flaskProcess = null;
  });
}

function waitForUrl(url, timeoutMs = 45000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (shuttingDown) return reject(new Error("shutdown"));
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) return resolve(true);
        retry();
      });
      req.on("error", retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        return reject(new Error(`Timeout esperando ${url}`));
      }
      setTimeout(tick, 350);
    };
    tick();
  });
}

function killFlaskTree() {
  if (!flaskProcess || !flaskProcess.pid) return;
  const pid = flaskProcess.pid;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
    } else {
      flaskProcess.kill("SIGTERM");
    }
  } catch (_) {
    /* ignore */
  }
  flaskProcess = null;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    title: "naw",
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#090a0d",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#0c0d12",
      symbolColor: "#9ca3af",
      height: 38,
    },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
    show: false,
  });

  const iconPath = path.join(ROOT, "static", "img", "icon.ico");
  try {
    mainWindow.setIcon(iconPath);
  } catch (_) {
    /* optional */
  }

  mainWindow.once("ready-to-show", () => mainWindow.show());

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  if (IS_DEV) {
    await waitForUrl(FLASK_URL + "/api/health").catch(() => {});
    try {
      await waitForUrl(VITE_URL, 20000);
      await mainWindow.loadURL(VITE_URL);
    } catch {
      await mainWindow.loadURL(FLASK_URL);
    }
  } else {
    await waitForUrl(FLASK_URL + "/api/health");
    await mainWindow.loadURL(FLASK_URL);
  }
}

app.whenReady().then(async () => {
  if (!HAS_LOCK) return;
  await startFlask();
  try {
    await createWindow();
    if (process.argv.includes("--smoke-test")) {
      await new Promise((resolve) => setTimeout(resolve, 800));
      const content = await mainWindow.webContents.executeJavaScript("document.getElementById('root')?.innerText || ''");
      if (!content.includes("Panel") || !content.includes("Objetos")) throw new Error("La interfaz no se pudo renderizar");
      require("fs").writeFileSync(process.env.NAW_SMOKE_RESULT, JSON.stringify({root:ROOT, rendered:true}));
      console.log("NAW_SMOKE_OK: Electron + Flask + interfaz compilada");
      app.quit();
    }
  } catch (err) {
    console.error("[electron] createWindow failed:", err);
    if (process.argv.includes("--smoke-test")) { app.exit(1); return; }
    if (mainWindow) {
      mainWindow.loadURL(
        "data:text/html;charset=utf-8," +
          encodeURIComponent(
            `<body style="background:#07080c;color:#f8fafc;font-family:sans-serif;padding:40px">
             <h2>naw no pudo arrancar</h2>
             <pre>${String(err)}</pre>
             <p>Revisá que Python esté instalado y el puerto ${FLASK_PORT} libre.</p>
             </body>`
          )
      );
      mainWindow.show();
    }
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", (event) => {
  if (!HAS_LOCK || cleanupFinished) return;
  event.preventDefault();
  if (cleanupStarted) return;
  cleanupStarted = true;
  shuttingDown = true;
  (async () => {
    try {
      if (await isFlaskUp() && !await stopProxy(FLASK_URL)) {
        console.error("[proxy] No se pudo confirmar la restauración de la red al cerrar. Revisá Logs.");
      }
    } catch (error) {
      console.error("[proxy] cleanup:", error);
    } finally {
      killFlaskTree();
      cleanupFinished = true;
      app.quit();
    }
  })();
});
