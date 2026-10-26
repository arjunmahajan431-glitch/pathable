import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Playwright webServer helper: start the real FastAPI backend in demo mode with
// a throwaway SQLite database. Keeping this in Node avoids a bash-only command
// so the same e2e run works on Windows and Linux.

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const isWindows = process.platform === 'win32';
const python = isWindows
  ? path.join(root, 'backend', '.venv', 'Scripts', 'python.exe')
  : path.join(root, 'backend', '.venv', 'bin', 'python');
const database = path.join(mkdtempSync(path.join(tmpdir(), 'pathable-e2e-')), 'reports.db');

const child = spawn(
  python,
  [
    '-m',
    'uvicorn',
    'pathable.api.main:app',
    '--host',
    '127.0.0.1',
    '--port',
    '8000',
  ],
  {
    cwd: path.join(root, 'backend'),
    env: {
      ...process.env,
      PATHABLE_DEMO: '1',
      PATHABLE_DATABASE: database,
      PATHABLE_ALLOWED_ORIGINS: 'http://127.0.0.1:5173,http://localhost:5173',
    },
    stdio: 'inherit',
  },
);

function shutdown() {
  if (!child.killed) child.kill();
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('exit', shutdown);

child.on('exit', (code) => {
  process.exit(code ?? 0);
});
