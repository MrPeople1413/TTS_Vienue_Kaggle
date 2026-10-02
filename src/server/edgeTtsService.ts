import { MsEdgeTTS, OUTPUT_FORMAT } from 'msedge-tts';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

const CACHE_DIR = path.resolve('cache');
if (!fs.existsSync(CACHE_DIR)) {
  fs.mkdirSync(CACHE_DIR, { recursive: true });
}

// In-memory cache for speed
const memoryCache = new Map<string, Buffer>();
const MAX_MEM_CACHE = 200;

export interface SynthesisOptions {
  text: string;
  voice?: string;
  speed?: number; // 0.5 to 2.0, default 1.0
  useCache?: boolean;
}

export function formatRate(speed: number = 1.0): string {
  const percent = Math.round((speed - 1) * 100);
  if (percent >= 0) {
    return `+${percent}%`;
  }
  return `${percent}%`;
}

export async function synthesizeSpeech(options: SynthesisOptions): Promise<Buffer> {
  const {
    text,
    voice = 'vi-VN-HoaiMyNeural',
    speed = 1.0,
    useCache = true,
  } = options;

  if (!text || !text.trim()) {
    throw new Error('Text to synthesize is empty');
  }

  // Normalize voice ID to supported Edge TTS Vietnamese voices
  let targetVoice = voice;
  if (
    voice.toLowerCase().includes('nam') ||
    voice.toLowerCase().includes('minh') ||
    voice.toLowerCase().includes('long') ||
    voice.toLowerCase().includes('male')
  ) {
    targetVoice = 'vi-VN-NamMinhNeural';
  } else if (
    voice !== 'vi-VN-NamMinhNeural' &&
    voice !== 'vi-VN-HoaiMyNeural'
  ) {
    targetVoice = 'vi-VN-HoaiMyNeural';
  }

  const cleanText = text.trim();
  const rateStr = formatRate(speed);
  const cacheKey = crypto
    .createHash('md5')
    .update(`${targetVoice}:${rateStr}:${cleanText}`)
    .digest('hex');

  // 1. Check memory cache
  if (useCache && memoryCache.has(cacheKey)) {
    return memoryCache.get(cacheKey)!;
  }

  // 2. Check disk cache
  const diskPath = path.join(CACHE_DIR, `${cacheKey}.mp3`);
  if (useCache && fs.existsSync(diskPath)) {
    try {
      const buf = fs.readFileSync(diskPath);
      memoryCache.set(cacheKey, buf);
      return buf;
    } catch {
      // Continue to fetch if disk read fails
    }
  }

  // 3. Synthesize via msedge-tts with timeout
  const tts = new MsEdgeTTS();
  
  return new Promise<Buffer>((resolve, reject) => {
    let timer: NodeJS.Timeout | null = null;
    let isSettled = false;

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      try {
        tts.close();
      } catch {
        // ignore close error
      }
    };

    timer = setTimeout(() => {
      if (!isSettled) {
        isSettled = true;
        cleanup();
        reject(new Error('Edge TTS synthesis timed out after 12s'));
      }
    }, 12000);

    (async () => {
      try {
        await tts.setMetadata(targetVoice, OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
        const { audioStream } = tts.toStream(cleanText, { rate: rateStr });
        const chunks: Buffer[] = [];

        audioStream.on('data', (data: Buffer | Uint8Array) => {
          chunks.push(Buffer.from(data));
        });

        audioStream.on('end', () => {
          if (isSettled) return;
          isSettled = true;
          cleanup();
          const buffer = Buffer.concat(chunks);
          if (buffer.length === 0) {
            return reject(new Error('TTS returned empty audio'));
          }

          // Save to cache
          if (useCache) {
            try {
              if (memoryCache.size >= MAX_MEM_CACHE) {
                const firstKey = memoryCache.keys().next().value;
                if (firstKey) memoryCache.delete(firstKey);
              }
              memoryCache.set(cacheKey, buffer);
              fs.writeFileSync(diskPath, buffer);
            } catch {
              // ignore cache write error
            }
          }

          resolve(buffer);
        });

        audioStream.on('error', (err) => {
          if (isSettled) return;
          isSettled = true;
          cleanup();
          reject(err);
        });
      } catch (err) {
        if (isSettled) return;
        isSettled = true;
        cleanup();
        reject(err);
      }
    })();
  });
}
