import fs from 'node:fs';
import path from 'node:path';
import { type Plugin } from 'vite';

const LOG_DIR = path.resolve(__dirname, '..', 'logs');
const LOG_FILE = path.join(LOG_DIR, 'dev.log');
const PID_FILE = path.join(LOG_DIR, 'frontend.pid');
const MAX_BYTES = 10 * 1024 * 1024; // 10 MB
const BACKUP_COUNT = 5;

// dev: local timezone; other: UTC (consistent with backend)
const USE_LOCAL_TIME = (process.env.OPENCOLAB_ENV || 'dev') === 'dev';

function formatTimestamp(): string {
  const d = new Date();
  if (USE_LOCAL_TIME) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    const s = String(d.getSeconds()).padStart(2, '0');
    return `${y}-${m}-${day} ${h}:${min}:${s}`;
  }
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

function rotateIfNeeded() {
  try {
    const stat = fs.statSync(LOG_FILE);
    if (stat.size < MAX_BYTES) return;

    // Rotate: dev.log.5 -> delete, dev.log.4 -> dev.log.5, ... dev.log -> dev.log.1
    for (let i = BACKUP_COUNT; i >= 1; i--) {
      const src = i === 1 ? LOG_FILE : `${LOG_FILE}.${i - 1}`;
      const dst = `${LOG_FILE}.${i}`;
      if (fs.existsSync(src)) {
        if (i === BACKUP_COUNT && fs.existsSync(dst)) fs.unlinkSync(dst);
        fs.renameSync(src, dst);
      }
    }
  } catch {
    // File may not exist yet
  }
}

function appendLog(level: string, msg: string) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
  rotateIfNeeded();
  const ts = formatTimestamp();
  const line = `${ts} | ${level.padEnd(8)} | ${msg}\n`;
  fs.appendFileSync(LOG_FILE, line, 'utf-8');
}

export default function viteLogFile(): Plugin {
  return {
    name: 'vite-log-file',
    configureServer(server) {
      appendLog('INFO', 'Vite dev server starting');

      server.httpServer?.on('listening', () => {
        const addr = server.httpServer?.address();
        const host = typeof addr === 'object' && addr ? `${addr.address}:${addr.port}` : String(addr);
        appendLog('INFO', `Vite dev server listening on ${host}`);

        // Write PID for process management (check status, stop)
        fs.mkdirSync(LOG_DIR, { recursive: true });
        fs.writeFileSync(PID_FILE, String(process.pid), 'utf-8');
      });

      server.httpServer?.on('close', () => {
        try {
          if (fs.existsSync(PID_FILE)) fs.unlinkSync(PID_FILE);
        } catch {
          // Ignore cleanup errors
        }
      });

      // Log proxy errors
      server.middlewares.use((req, _res, next) => {
        const start = Date.now();
        _res.on('finish', () => {
          const duration = Date.now() - start;
          if (_res.statusCode >= 400) {
            appendLog('WARN', `${req.method} ${req.url} -> ${_res.statusCode} (${duration}ms)`);
          }
        });
        next();
      });
    },
    buildStart() {
      appendLog('INFO', 'Build started');
    },
    buildEnd(error) {
      if (error) {
        appendLog('ERROR', `Build failed: ${error.message}`);
      } else {
        appendLog('INFO', 'Build completed');
      }
    },
  };
}
