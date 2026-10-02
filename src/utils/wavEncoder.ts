/**
 * Encodes Float32Array PCM audio samples into a standard RIFF WAV Blob (16-bit PCM Mono).
 */
export function pcmToWavBlob(samples: Float32Array, sampleRate: number = 24000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // Helper to write ASCII string to DataView
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  /* RIFF identifier */
  writeString(0, 'RIFF');
  /* file length */
  view.setUint32(4, 36 + samples.length * 2, true);
  /* RIFF type */
  writeString(8, 'WAVE');
  /* format chunk identifier */
  writeString(12, 'fmt ');
  /* format chunk length */
  view.setUint32(16, 16, true);
  /* sample format (raw PCM = 1) */
  view.setUint16(20, 1, true);
  /* channel count (Mono = 1) */
  view.setUint16(22, 1, true);
  /* sample rate */
  view.setUint32(24, sampleRate, true);
  /* byte rate (sampleRate * 1 * 2) */
  view.setUint32(28, sampleRate * 2, true);
  /* block align (1 * 2) */
  view.setUint16(32, 2, true);
  /* bits per sample (16 bit) */
  view.setUint16(34, 16, true);
  /* data chunk identifier */
  writeString(36, 'data');
  /* data chunk length */
  view.setUint32(40, samples.length * 2, true);

  // Write PCM 16-bit samples
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

/**
 * Decodes an array of MP3 Blobs/ArrayBuffers and combines them seamlessly into a single .wav Blob.
 */
export async function convertMp3BlobsToWav(blobs: Blob[]): Promise<Blob> {
  const AudioContextClass =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;

  const audioCtx = new AudioContextClass();

  try {
    const decodedBuffers: AudioBuffer[] = [];
    let totalSamples = 0;
    let sampleRate = 24000;

    for (const blob of blobs) {
      const arrayBuffer = await blob.arrayBuffer();
      // decodeAudioData consumes the buffer, so slice it
      const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
      decodedBuffers.push(audioBuffer);
      totalSamples += audioBuffer.length;
      sampleRate = audioBuffer.sampleRate;
    }

    // Merge all channel 0 data into one Float32Array
    const mergedSamples = new Float32Array(totalSamples);
    let currentOffset = 0;

    for (const buf of decodedBuffers) {
      const channelData = buf.getChannelData(0);
      mergedSamples.set(channelData, currentOffset);
      currentOffset += buf.length;
    }

    return pcmToWavBlob(mergedSamples, sampleRate);
  } finally {
    try {
      await audioCtx.close();
    } catch {
      // ignore
    }
  }
}
