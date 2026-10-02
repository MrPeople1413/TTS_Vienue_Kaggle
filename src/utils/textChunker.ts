export interface TextChunk {
  id: number;
  text: string;
  startIndex: number;
  endIndex: number;
}

/**
 * Splits text into natural sentence-based chunks, roughly matching targetChunkSize
 * without cutting words or sentences unnaturally.
 */
export function splitIntoChunks(content: string, targetChunkSize: number = 180): TextChunk[] {
  if (!content || !content.trim()) return [];

  // Normalize newlines
  const normalized = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // Split into paragraphs first
  const paragraphs = normalized.split(/\n+/);
  const chunks: TextChunk[] = [];
  let currentId = 0;
  let charPointer = 0;

  for (const para of paragraphs) {
    const trimmedPara = para.trim();
    if (!trimmedPara) continue;

    // Split paragraph into sentence segments using punctuation (. ! ? ...)
    const sentenceRegex = /([^.!?…]+[.!?…]+|[^.!?…]+$)/g;
    const sentences = trimmedPara.match(sentenceRegex) || [trimmedPara];

    let currentAccumulator = '';
    let accStartIndex = charPointer;

    for (const sent of sentences) {
      const cleanSent = sent.trim();
      if (!cleanSent) continue;

      if ((currentAccumulator + ' ' + cleanSent).trim().length > targetChunkSize && currentAccumulator.length > 0) {
        chunks.push({
          id: currentId++,
          text: currentAccumulator.trim(),
          startIndex: accStartIndex,
          endIndex: accStartIndex + currentAccumulator.length,
        });
        currentAccumulator = cleanSent;
        accStartIndex = charPointer;
      } else {
        if (currentAccumulator.length > 0) {
          currentAccumulator += ' ' + cleanSent;
        } else {
          currentAccumulator = cleanSent;
          accStartIndex = charPointer;
        }
      }
      charPointer += sent.length;
    }

    if (currentAccumulator.trim().length > 0) {
      chunks.push({
        id: currentId++,
        text: currentAccumulator.trim(),
        startIndex: accStartIndex,
        endIndex: accStartIndex + currentAccumulator.length,
      });
    }
  }

  return chunks;
}
