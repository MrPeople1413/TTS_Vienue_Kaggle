import express from 'express';
import cors from 'cors';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { ZipArchive } from 'archiver';
import { synthesizeSpeech } from './src/server/edgeTtsService.js';
import { SAMPLE_STORIES } from './src/server/sampleStories.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = Number(process.env.PORT || 3000);

app.use(cors());
app.use(express.json({ limit: '20mb' }));

const CONFIG_DIR = path.resolve('config');
const SETTINGS_FILE = path.join(CONFIG_DIR, 'settings.json');
const POSITIONS_FILE = path.join(CONFIG_DIR, 'positions.json');

// Ensure config dir exists
if (!fs.existsSync(CONFIG_DIR)) {
  fs.mkdirSync(CONFIG_DIR, { recursive: true });
}

// Default settings
const DEFAULT_SETTINGS = {
  engine: 'edge_tts',
  edge_voice: 'vi-VN-HoaiMyNeural',
  vieneu_voice: 'custom::vn_despina_6',
  vieneu_device: 'cpu',
  speed: 1.0,
  volume: 1.0,
  chunk_size: 180,
  export_workers: 4,
  vieneu_threads: 8,
  auto_next: true,
  use_cache: true,
  kaggle_dataset_slug: 'viettt-tts-input',
  kaggle_kernel_slug: 'mrpeople1413/vieneu-tts-server',
  kaggle_batch_voice: 'Ngọc Lan — nữ, giọng dịu dàng',
  kaggle_batch_size: 10,
  kaggle_poll_sec: 40,
};

function readSettings() {
  try {
    if (fs.existsSync(SETTINGS_FILE)) {
      const data = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf-8'));
      return { ...DEFAULT_SETTINGS, ...data };
    }
  } catch (err) {
    console.error('Error reading settings.json:', err);
  }
  return DEFAULT_SETTINGS;
}

function writeSettings(newSettings: Record<string, any>) {
  try {
    const current = readSettings();
    const merged = { ...current, ...newSettings };
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(merged, null, 2), 'utf-8');
    return merged;
  } catch (err) {
    console.error('Error writing settings.json:', err);
    throw err;
  }
}

function readPositions() {
  try {
    if (fs.existsSync(POSITIONS_FILE)) {
      return JSON.parse(fs.readFileSync(POSITIONS_FILE, 'utf-8'));
    }
  } catch (err) {
    console.error('Error reading positions.json:', err);
  }
  return {};
}

function writePositions(positions: Record<string, any>) {
  try {
    fs.writeFileSync(POSITIONS_FILE, JSON.stringify(positions, null, 2), 'utf-8');
    return positions;
  } catch (err) {
    console.error('Error writing positions.json:', err);
    throw err;
  }
}

// ── API ROUTES ─────────────────────────────────────────────────────────────

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', time: new Date().toISOString() });
});

// Settings
app.get('/api/settings', (req, res) => {
  res.json(readSettings());
});

app.post('/api/settings', (req, res) => {
  try {
    const updated = writeSettings(req.body);
    res.json({ success: true, settings: updated });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Reading positions (auto-saved)
app.get('/api/positions', (req, res) => {
  res.json(readPositions());
});

app.post('/api/positions', (req, res) => {
  try {
    const updated = writePositions(req.body);
    res.json({ success: true, positions: updated });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Sample stories
app.get('/api/stories', (req, res) => {
  res.json(SAMPLE_STORIES);
});

// Voices list
app.get('/api/voices', (req, res) => {
  res.json([
    {
      id: 'vi-VN-HoaiMyNeural',
      name: 'Hoài My (Nữ - Truyền cảm, tự nhiên)',
      gender: 'Female',
      locale: 'vi-VN',
      engine: 'edge_tts',
      recommended: true,
    },
    {
      id: 'vi-VN-NamMinhNeural',
      name: 'Nam Minh (Nam - Trầm ấm, dõng dạc)',
      gender: 'Male',
      locale: 'vi-VN',
      engine: 'edge_tts',
      recommended: true,
    },
    {
      id: 'browser-native',
      name: 'Trình duyệt Web Speech (Offline / Fallback)',
      gender: 'Neutral',
      locale: 'vi-VN',
      engine: 'browser',
      recommended: false,
    },
  ]);
});

// Text-to-Speech synthesis endpoint
app.post('/api/tts/synthesize', async (req, res) => {
  try {
    const { text, voice = 'vi-VN-HoaiMyNeural', speed = 1.0, useCache = true } = req.body;

    if (!text || typeof text !== 'string' || !text.trim()) {
      return res.status(400).json({ error: 'Nội dung văn bản trống.' });
    }

    const audioBuffer = await synthesizeSpeech({
      text,
      voice,
      speed: Number(speed) || 1.0,
      useCache: useCache !== false,
    });

    res.set({
      'Content-Type': 'audio/mpeg',
      'Content-Length': audioBuffer.length,
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'public, max-age=86400',
    });

    res.send(audioBuffer);
  } catch (err: any) {
    console.error('Synthesis error:', err);
    res.status(500).json({
      error: err.message || 'Lỗi tổng hợp giọng nói Edge TTS',
      fallbackToBrowser: true,
    });
  }
});

// Kaggle notebook generator
app.post('/api/kaggle/generate-notebook', (req, res) => {
  try {
    const notebookPath = path.resolve('kaggle_notebook_tts.py');
    if (fs.existsSync(notebookPath)) {
      const pythonCode = fs.readFileSync(notebookPath, 'utf-8');
      return res.json({
        success: true,
        pythonCode,
        filename: 'kaggle_notebook_tts.py',
      });
    }

    res.status(404).json({ error: 'File kaggle_notebook_tts.py không tồn tại.' });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Kaggle connector script
app.get('/api/kaggle/connector-script', (req, res) => {
  try {
    const connectorPath = path.resolve('kaggle_connector.py');
    if (fs.existsSync(connectorPath)) {
      res.setHeader('Content-Type', 'text/x-python; charset=utf-8');
      res.setHeader('Content-Disposition', 'attachment; filename="kaggle_connector.py"');
      return res.sendFile(connectorPath);
    }
    res.status(404).json({ error: 'File kaggle_connector.py không tồn tại.' });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Kaggle input.zip package exporter
app.post('/api/kaggle/export-zip', (req, res) => {
  try {
    const {
      chapters = [],
      voice = 'Ngọc Lan — nữ, giọng dịu dàng',
      speed = 1.0,
      format = 'wav',
      groupSize = 10,
      username = 'username',
      datasetSlug = 'viettt-tts-input',
    } = req.body;

    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="input.zip"`);

    const archive = new ZipArchive({ zlib: { level: 9 } });

    archive.on('error', (err: any) => {
      console.error('Archive error:', err);
      res.status(500).send({ error: err.message });
    });

    archive.pipe(res);

    // Natural sort chapters
    const sortedChapters = [...chapters].sort((a: any, b: any) => {
      const titleA = a.title || a.id || '';
      const titleB = b.title || b.id || '';
      return titleA.localeCompare(titleB, undefined, { numeric: true, sensitivity: 'base' });
    });

    const metadata = {
      version: '2.2',
      created_at: Date.now(),
      voice_id: voice,
      speed: Number(speed) || 1.0,
      format: format || 'wav',
      group_size: Number(groupSize) || 10,
      total_chapters: sortedChapters.length,
      files: [] as any[],
    };

    sortedChapters.forEach((ch: any, idx: number) => {
      const padIdx = String(idx + 1).padStart(4, '0');
      const safeTitle = (ch.title || `chap_${idx + 1}`).replace(/[/\\?%*:|"<> ]/g, '_');
      const filename = `chap_${padIdx}_${safeTitle}.txt`;
      const content = (ch.content || '').trim();

      archive.append(content, { name: filename });
      metadata.files.push({
        index: idx + 1,
        filename,
        title: ch.title || `Chương ${idx + 1}`,
        words: content.split(/\s+/).length,
      });
    });

    archive.append(JSON.stringify(metadata, null, 2), { name: 'metadata.json' });

    const datasetMetadata = {
      title: `Vietnamese TTS Input Package (${datasetSlug})`,
      id: `${username}/${datasetSlug}`,
      licenses: [{ name: 'CC0-1.0' }],
    };
    archive.append(JSON.stringify(datasetMetadata, null, 2), { name: 'dataset-metadata.json' });

    archive.finalize();
  } catch (err: any) {
    console.error('Error generating input.zip:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── VITE MIDDLEWARE OR STATIC SERVING ──────────────────────────────────────

async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const { createServer } = await import('vite');
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve('dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.resolve('dist/index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[TTS Server] Running on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
