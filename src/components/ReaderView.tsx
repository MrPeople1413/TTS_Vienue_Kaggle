import React, { useEffect, useRef } from 'react';
import { Chapter } from '../types';
import { TextChunk } from '../utils/textChunker';
import { Volume2, Clock, FileText, ChevronLeft, ChevronRight, Play } from 'lucide-react';

interface ReaderViewProps {
  chapter: Chapter;
  chunks: TextChunk[];
  currentChunkIndex: number;
  isPlaying: boolean;
  onPlayChunk: (index: number) => void;
  onPrevChapter?: () => void;
  onNextChapter?: () => void;
  hasPrevChapter: boolean;
  hasNextChapter: boolean;
  theme: 'dark' | 'black' | 'sepia' | 'light';
  fontSize: 'sm' | 'base' | 'lg' | 'xl';
  fontFamily: 'serif' | 'sans';
}

export const ReaderView: React.FC<ReaderViewProps> = ({
  chapter,
  chunks,
  currentChunkIndex,
  isPlaying,
  onPlayChunk,
  onPrevChapter,
  onNextChapter,
  hasPrevChapter,
  hasNextChapter,
  theme,
  fontSize,
  fontFamily,
}) => {
  const activeChunkRef = useRef<HTMLSpanElement | null>(null);

  // Auto-scroll active chunk into view
  useEffect(() => {
    if (activeChunkRef.current) {
      activeChunkRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [currentChunkIndex]);

  // Word count & estimated audio time
  const wordCount = chapter.content.trim().split(/\s+/).length;
  const estimatedMinutes = Math.ceil(wordCount / 130); // ~130 wpm in Vietnamese TTS

  // Theme styling classes
  const themeClasses = {
    dark: 'bg-neutral-900 text-neutral-200',
    black: 'bg-black text-neutral-300',
    sepia: 'bg-[#f7f1e5] text-[#3d3228]',
    light: 'bg-white text-neutral-800',
  }[theme];

  const cardBgClasses = {
    dark: 'bg-neutral-800/40 border-neutral-800',
    black: 'bg-neutral-900/60 border-neutral-800',
    sepia: 'bg-[#ede3cf]/60 border-[#decbb1]',
    light: 'bg-neutral-50 border-neutral-200',
  }[theme];

  const activeHighlightClasses = {
    dark: 'bg-indigo-600/30 text-white border-l-4 border-indigo-500 shadow-sm shadow-indigo-950',
    black: 'bg-indigo-900/50 text-indigo-100 border-l-4 border-indigo-400',
    sepia: 'bg-[#d8c29d]/70 text-[#271d15] border-l-4 border-[#8c6d46]',
    light: 'bg-indigo-100 text-indigo-950 border-l-4 border-indigo-600',
  }[theme];

  const fontSizeClasses = {
    sm: 'text-sm leading-relaxed',
    base: 'text-base leading-relaxed',
    lg: 'text-lg leading-loose',
    xl: 'text-xl leading-loose',
  }[fontSize];

  const fontClass = fontFamily === 'serif' ? 'font-reader-serif' : 'font-reader-sans';

  return (
    <div className={`min-h-[calc(100vh-8rem)] pb-36 transition-colors duration-200 ${themeClasses}`}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        {/* Chapter Header Card */}
        <div className={`p-6 sm:p-8 rounded-2xl border mb-8 transition-colors ${cardBgClasses}`}>
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-3 text-xs opacity-75">
              <span className="flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" />
                {wordCount.toLocaleString()} từ
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                Khoảng {estimatedMinutes} phút nghe
              </span>
              <span>•</span>
              <span>{chunks.length} đoạn câu</span>
            </div>

            {/* Quick chapter switcher */}
            <div className="flex items-center gap-1 text-xs">
              <button
                onClick={onPrevChapter}
                disabled={!hasPrevChapter}
                className="p-1.5 rounded-lg border border-current/20 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                title="Chương trước"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={onNextChapter}
                disabled={!hasNextChapter}
                className="p-1.5 rounded-lg border border-current/20 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                title="Chương sau"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          <h1 className={`text-2xl sm:text-3xl font-bold tracking-tight mb-2 ${fontClass}`}>
            {chapter.title}
          </h1>

          {chapter.author && (
            <p className="text-sm opacity-80 italic">
              Tác giả: {chapter.author} {chapter.source ? `| Nguồn: ${chapter.source}` : ''}
            </p>
          )}

          {/* Reading progress in chapter */}
          <div className="mt-5 pt-4 border-t border-current/10">
            <div className="flex items-center justify-between text-xs opacity-70 mb-1.5">
              <span>Tiến độ nghe hiện tại:</span>
              <span className="font-mono">
                {chunks.length > 0
                  ? `${Math.round(((currentChunkIndex + 1) / chunks.length) * 100)}% (${currentChunkIndex + 1}/${chunks.length})`
                  : '0%'}
              </span>
            </div>
            <div className="w-full h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                style={{
                  width: chunks.length > 0 ? `${((currentChunkIndex + 1) / chunks.length) * 100}%` : '0%',
                }}
              />
            </div>
          </div>
        </div>

        {/* Content Paragraphs / Sentence Chunks */}
        <div className={`space-y-4 ${fontClass} ${fontSizeClasses}`}>
          {chunks.length === 0 ? (
            <div className="text-center py-12 opacity-60">
              <p>Chưa có nội dung văn bản. Vui lòng thêm truyện hoặc tải file .txt.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {chunks.map((chunk, index) => {
                const isActive = index === currentChunkIndex;

                return (
                  <div
                    key={chunk.id}
                    onClick={() => onPlayChunk(index)}
                    className={`group relative p-3 rounded-xl transition-all duration-150 cursor-pointer ${
                      isActive
                        ? `${activeHighlightClasses} pl-4 font-medium`
                        : 'hover:bg-black/5 dark:hover:bg-white/5 opacity-85 hover:opacity-100'
                    }`}
                  >
                    {isActive && (
                      <span
                        ref={activeChunkRef}
                        className="inline-flex items-center gap-1.5 mr-2 text-indigo-400 font-bold"
                      >
                        {isPlaying ? (
                          <Volume2 className="w-4 h-4 animate-pulse inline text-indigo-500 dark:text-indigo-400" />
                        ) : (
                          <Play className="w-3.5 h-3.5 inline text-neutral-400" />
                        )}
                      </span>
                    )}

                    <span>{chunk.text}</span>

                    {/* Small hover indicator */}
                    {!isActive && (
                      <span className="opacity-0 group-hover:opacity-60 transition-opacity ml-2 text-xs text-indigo-400">
                        ▶ Đọc từ đây
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* End of chapter actions */}
        {chunks.length > 0 && (
          <div className="mt-12 pt-8 border-t border-current/10 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
            <p className="opacity-60">Bạn đã xem hết nội dung chương này.</p>
            {hasNextChapter && (
              <button
                onClick={onNextChapter}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl font-medium shadow-md shadow-indigo-600/20 transition-colors"
              >
                Chuyển sang chương tiếp theo
                <ChevronRight className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
