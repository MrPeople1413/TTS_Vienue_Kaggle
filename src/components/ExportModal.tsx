import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  X,
  Download,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Layers,
  FileAudio,
  Play,
  Pause,
  RotateCcw,
  Sparkles,
  Check,
  Disc,
} from 'lucide-react';
import { Chapter } from '../types';
import { splitIntoChunks, TextChunk } from '../utils/textChunker';
import { convertMp3BlobsToWav } from '../utils/wavEncoder';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  chapters: Chapter[];
  currentChapterId: string;
  voice: string;
  speed: number;
  chunkSize?: number;
}

interface ExportGroupItem {
  id: string;
  name: string;
  chapterIndices: number[];
  chapterTitles: string[];
  totalWords: number;
  status: 'pending' | 'processing' | 'done' | 'error';
  audioBlob?: Blob;
  audioUrl?: string;
  error?: string;
  progressPercent: number;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  chapters,
  currentChapterId,
  voice,
  speed,
  chunkSize = 180,
}) => {
  // Export Mode: 'grouped' (batch gộp chương) or 'single' (1 chương)
  const [exportMode, setExportMode] = useState<'grouped' | 'single'>('grouped');

  // Export Format: 'mp3' or 'wav'
  const [exportFormat, setExportFormat] = useState<'mp3' | 'wav'>('mp3');

  // Selected chapters for grouped export
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>(
    chapters.map((c) => c.id)
  );

  // Group size: default 10 chapters per file
  const [groupSize, setGroupSize] = useState<number>(10);
  const [customGroupSize, setCustomGroupSize] = useState<string>('10');
  const [autoDownloadEach, setAutoDownloadEach] = useState<boolean>(true);

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [currentGroupIndex, setCurrentGroupIndex] = useState<number>(0);
  const [statusText, setStatusText] = useState<string>('');
  const [overallProgress, setOverallProgress] = useState<number>(0);
  const [fileProgress, setFileProgress] = useState<number>(0);
  const [completedList, setCompletedList] = useState<
    { name: string; url: string; sizeMb: string; chaptersCount: number; format: string }[]
  >([]);

  // Refs for pause/cancel
  const cancelRef = useRef(false);
  const isPausedRef = useRef(false);

  // Update selected chapters when chapters change
  useEffect(() => {
    setSelectedChapterIds(chapters.map((c) => c.id));
  }, [chapters]);

  // Sync ref
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // The ordered list of selected chapters
  const selectedChapters = useMemo(() => {
    return chapters.filter((c) => selectedChapterIds.includes(c.id));
  }, [chapters, selectedChapterIds]);

  // Current single chapter
  const currentChapter = useMemo(() => {
    return chapters.find((c) => c.id === currentChapterId) || chapters[0];
  }, [chapters, currentChapterId]);

  // Calculate grouped packages
  const plannedGroups = useMemo<ExportGroupItem[]>(() => {
    if (exportMode === 'single') {
      if (!currentChapter) return [];
      const wordCount = currentChapter.content.trim().split(/\s+/).length;
      return [
        {
          id: 'single-1',
          name: currentChapter.title.replace(/[/\\?%*:|"<>]/g, '_'),
          chapterIndices: [0],
          chapterTitles: [currentChapter.title],
          totalWords: wordCount,
          status: 'pending',
          progressPercent: 0,
        },
      ];
    }

    if (selectedChapters.length === 0) return [];

    const effectiveSize = Math.max(1, groupSize);
    const groups: ExportGroupItem[] = [];

    for (let i = 0; i < selectedChapters.length; i += effectiveSize) {
      const slice = selectedChapters.slice(i, i + effectiveSize);
      const startNum = i + 1;
      const endNum = i + slice.length;
      const padStart = String(startNum).padStart(3, '0');
      const padEnd = String(endNum).padStart(3, '0');

      const name =
        slice.length === 1
          ? `Chuong_${padStart}_${slice[0].title.replace(/[/\\?%*:|"<>]/g, '_').substring(0, 30)}`
          : `Gop_Chuong_${padStart}_den_${padEnd}`;

      const totalWords = slice.reduce(
        (acc, c) => acc + c.content.trim().split(/\s+/).length,
        0
      );

      groups.push({
        id: `group-${i}`,
        name,
        chapterIndices: slice.map((_, idx) => i + idx),
        chapterTitles: slice.map((c) => c.title),
        totalWords,
        status: 'pending',
        progressPercent: 0,
      });
    }

    return groups;
  }, [exportMode, selectedChapters, groupSize, currentChapter]);

  if (!isOpen) return null;

  // Toggle chapter selection
  const toggleSelectChapter = (id: string) => {
    setSelectedChapterIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const selectAll = () => setSelectedChapterIds(chapters.map((c) => c.id));
  const deselectAll = () => setSelectedChapterIds([]);

  // Check pause state
  const waitIfPaused = async () => {
    while (isPausedRef.current && !cancelRef.current) {
      await new Promise((r) => setTimeout(r, 200));
    }
  };

  // Run the batch pipeline sequentially until done
  const handleStartExport = async () => {
    if (plannedGroups.length === 0) return;

    setIsProcessing(true);
    setIsPaused(false);
    cancelRef.current = false;
    setCompletedList([]);
    setOverallProgress(0);
    setFileProgress(0);

    const totalGroups = plannedGroups.length;

    try {
      for (let gIdx = 0; gIdx < totalGroups; gIdx++) {
        if (cancelRef.current) break;

        setCurrentGroupIndex(gIdx);
        const group = plannedGroups[gIdx];
        setStatusText(
          `Đang xử lý Tập ${gIdx + 1}/${totalGroups} (${group.chapterTitles.length} chương)...`
        );

        const groupAudioBlobs: Blob[] = [];
        const chaptersInThisGroup = group.chapterIndices.map(
          (idx) => selectedChapters[idx]
        );

        // Collect all chunks across all chapters in this group
        const allChunksWithInfo: { chunk: TextChunk; chapterTitle: string; chapIdx: number }[] = [];
        chaptersInThisGroup.forEach((chap, cIdx) => {
          const chChunks = splitIntoChunks(chap.content, chunkSize);
          chChunks.forEach((ck) => {
            allChunksWithInfo.push({
              chunk: ck,
              chapterTitle: chap.title,
              chapIdx: cIdx + 1,
            });
          });
        });

        const totalChunksInGroup = allChunksWithInfo.length;

        // Process chunks sequentially
        for (let cIdx = 0; cIdx < totalChunksInGroup; cIdx++) {
          if (cancelRef.current) break;
          await waitIfPaused();
          if (cancelRef.current) break;

          const item = allChunksWithInfo[cIdx];
          setStatusText(
            `Tập ${gIdx + 1}/${totalGroups}: Đang đọc ${item.chapterTitle} (Đoạn ${cIdx + 1}/${totalChunksInGroup})`
          );

          // Synthesize chunk
          let res = await fetch('/api/tts/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              text: item.chunk.text,
              voice,
              speed,
              useCache: true,
            }),
          });

          // Retry once on failure
          if (!res.ok) {
            await new Promise((r) => setTimeout(r, 600));
            res = await fetch('/api/tts/synthesize', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                text: item.chunk.text,
                voice,
                speed,
                useCache: true,
              }),
            });
          }

          if (!res.ok) {
            throw new Error(`Lỗi tổng hợp âm thanh đoạn ${cIdx + 1} của ${item.chapterTitle}`);
          }

          const blob = await res.blob();
          groupAudioBlobs.push(blob);

          const curPercent = Math.round(((cIdx + 1) / totalChunksInGroup) * 100);
          setFileProgress(curPercent);

          const overall = Math.round(
            ((gIdx + (cIdx + 1) / totalChunksInGroup) / totalGroups) * 100
          );
          setOverallProgress(overall);
        }

        if (cancelRef.current) break;

        // Format conversion: WAV or MP3
        let finalBlob: Blob;
        let fileName: string;

        if (exportFormat === 'wav') {
          setStatusText(`Đang kết xuất định dạng WAV (16-bit PCM không nén) cho Tập ${gIdx + 1}...`);
          finalBlob = await convertMp3BlobsToWav(groupAudioBlobs);
          fileName = `${group.name}.wav`;
        } else {
          finalBlob = new Blob(groupAudioBlobs, { type: 'audio/mpeg' });
          fileName = `${group.name}.mp3`;
        }

        const audioUrl = URL.createObjectURL(finalBlob);
        const sizeMb = (finalBlob.size / (1024 * 1024)).toFixed(2) + ' MB';

        // Add to completed list
        setCompletedList((prev) => [
          ...prev,
          {
            name: fileName,
            url: audioUrl,
            sizeMb,
            chaptersCount: chaptersInThisGroup.length,
            format: exportFormat.toUpperCase(),
          },
        ]);

        // Auto download if enabled
        if (autoDownloadEach) {
          const a = document.createElement('a');
          a.href = audioUrl;
          a.download = fileName;
          a.click();
        }
      }

      if (cancelRef.current) {
        setStatusText('Đã dừng tiến trình xuất file.');
      } else {
        setStatusText(`Hoàn thành xuất toàn bộ ${totalGroups} file âm thanh (${exportFormat.toUpperCase()})!`);
        setOverallProgress(100);
        setFileProgress(100);
      }
    } catch (err: any) {
      console.error('Export batch error:', err);
      setStatusText(`Lỗi: ${err.message || 'Xảy ra sự cố khi xuất âm thanh'}`);
    } finally {
      setIsProcessing(false);
      setIsPaused(false);
    }
  };

  const handleCancel = () => {
    cancelRef.current = true;
    setIsProcessing(false);
    setIsPaused(false);
  };

  const handleTogglePause = () => {
    setIsPaused(!isPaused);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl max-w-2xl w-full p-5 sm:p-6 text-neutral-100 shadow-2xl overflow-y-auto max-h-[92vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-neutral-800 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-emerald-600/20 text-emerald-400 border border-emerald-500/30">
              <Download className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Xuất Audio (MP3 / WAV) & Gộp Chương</h2>
              <p className="text-xs text-neutral-400">
                Tùy chọn xuất file .MP3 hoặc .WAV, ghép nhiều chương (VD: 10 chương/file)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isProcessing}
            className="p-1.5 text-neutral-400 hover:text-white rounded-lg hover:bg-neutral-800 transition-colors disabled:opacity-40"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mode selector */}
        {!isProcessing && (
          <div className="space-y-3 mb-4">
            <div className="grid grid-cols-2 gap-2 p-1 bg-neutral-800/60 rounded-xl border border-neutral-700/60 text-xs">
              <button
                onClick={() => setExportMode('grouped')}
                className={`flex items-center justify-center gap-1.5 py-2 rounded-lg font-medium transition-all ${
                  exportMode === 'grouped'
                    ? 'bg-emerald-600 text-white shadow'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                <Layers className="w-4 h-4" />
                Gộp nhiều chương (Hàng loạt)
              </button>
              <button
                onClick={() => setExportMode('single')}
                className={`flex items-center justify-center gap-1.5 py-2 rounded-lg font-medium transition-all ${
                  exportMode === 'single'
                    ? 'bg-emerald-600 text-white shadow'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                <FileAudio className="w-4 h-4" />
                Chỉ xuất 1 chương hiện tại
              </button>
            </div>

            {/* Audio format selector (.MP3 or .WAV) */}
            <div className="flex items-center justify-between p-3 rounded-xl bg-neutral-800/40 border border-neutral-700/60 text-xs">
              <div className="pr-3">
                <span className="font-semibold text-neutral-200 flex items-center gap-1.5">
                  <Disc className="w-4 h-4 text-emerald-400" />
                  Định dạng âm thanh:
                </span>
                <p className="text-[11px] text-neutral-400 mt-0.5">
                  {exportFormat === 'wav'
                    ? 'WAV: Âm thanh chất lượng cao 16-bit PCM không nén, phù hợp dựng phim, chỉnh sửa podcast, không suy hao tín hiệu'
                    : 'MP3: Nén nhỏ gọn, dung lượng nhẹ, dễ dàng phát trên điện thoại và chia sẻ nhanh'}
                </p>
              </div>
              <div className="flex items-center gap-1 bg-neutral-900 p-1 rounded-xl border border-neutral-700 shrink-0">
                <button
                  onClick={() => setExportFormat('mp3')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    exportFormat === 'mp3'
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-neutral-400 hover:text-white'
                  }`}
                >
                  .MP3
                </button>
                <button
                  onClick={() => setExportFormat('wav')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    exportFormat === 'wav'
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-neutral-400 hover:text-white'
                  }`}
                >
                  .WAV
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Configuration for Grouped Mode */}
        {exportMode === 'grouped' && !isProcessing && (
          <div className="space-y-4 mb-4 text-xs">
            {/* Group size configuration */}
            <div className="bg-neutral-800/40 border border-neutral-700/60 rounded-xl p-3.5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-neutral-200 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  Số chương gộp vào 1 file audio:
                </span>
                <div className="flex items-center gap-1">
                  {[1, 5, 10, 20].map((sz) => (
                    <button
                      key={sz}
                      onClick={() => {
                        setGroupSize(sz);
                        setCustomGroupSize(String(sz));
                      }}
                      className={`px-2.5 py-1 rounded-lg border font-mono transition-colors ${
                        groupSize === sz
                          ? 'bg-emerald-600 border-emerald-500 text-white font-bold'
                          : 'bg-neutral-800 border-neutral-700 text-neutral-300 hover:bg-neutral-700'
                      }`}
                    >
                      {sz === 1 ? '1 chap' : `${sz} chap`}
                    </button>
                  ))}
                  <div className="flex items-center gap-1 ml-1 pl-2 border-l border-neutral-700">
                    <span className="text-neutral-400">Tùy chỉnh:</span>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={customGroupSize}
                      onChange={(e) => {
                        setCustomGroupSize(e.target.value);
                        const val = Number(e.target.value);
                        if (val > 0) setGroupSize(val);
                      }}
                      className="w-12 bg-neutral-900 border border-neutral-700 rounded px-1.5 py-1 text-center text-white font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Summary note */}
              <div className="text-[11px] text-neutral-400 flex items-center justify-between border-t border-neutral-700/40 pt-2">
                <span>
                  Đã chọn <b>{selectedChapters.length}</b>/{chapters.length} chương.
                </span>
                <span className="text-emerald-400 font-semibold">
                  Dự kiến xuất: <b>{plannedGroups.length} file .{exportFormat.toUpperCase()}</b> ({groupSize} chap/file)
                </span>
              </div>
            </div>

            {/* Chapters list selector */}
            <div className="bg-neutral-800/40 border border-neutral-700/60 rounded-xl p-3.5 space-y-2">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-neutral-200">
                  Chọn các chương cần xuất:
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={selectAll}
                    className="text-indigo-400 hover:underline"
                  >
                    Chọn tất cả
                  </button>
                  <span>|</span>
                  <button
                    onClick={deselectAll}
                    className="text-neutral-400 hover:text-white"
                  >
                    Bỏ chọn
                  </button>
                </div>
              </div>

              <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                {chapters.map((ch, idx) => {
                  const isChecked = selectedChapterIds.includes(ch.id);
                  return (
                    <div
                      key={ch.id}
                      onClick={() => toggleSelectChapter(ch.id)}
                      className={`flex items-center justify-between p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                        isChecked
                          ? 'bg-emerald-950/30 border-emerald-700/50 text-emerald-200'
                          : 'bg-neutral-900/40 border-neutral-800 text-neutral-400 hover:border-neutral-700'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <span className="w-5 h-4 rounded bg-black/40 text-[10px] font-mono flex items-center justify-center shrink-0">
                          {idx + 1}
                        </span>
                        <span className="truncate max-w-sm">{ch.title}</span>
                      </div>
                      <span className="font-mono text-[11px] opacity-70">
                        {ch.content.trim().split(/\s+/).length} từ
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Preview of Output Files */}
            <div className="bg-neutral-800/40 border border-neutral-700/60 rounded-xl p-3.5 space-y-2">
              <span className="font-semibold text-neutral-200 block mb-1">
                Danh sách các file sẽ xuất tuần tự ({plannedGroups.length} file .{exportFormat.toUpperCase()}):
              </span>
              <div className="max-h-28 overflow-y-auto space-y-1 pr-1 font-mono text-[11px]">
                {plannedGroups.map((g, i) => (
                  <div
                    key={g.id}
                    className="flex items-center justify-between p-1.5 rounded bg-neutral-900/60 border border-neutral-800 text-neutral-300"
                  >
                    <span className="truncate max-w-md">
                      File {i + 1}: <b>{g.name}.{exportFormat}</b>
                    </span>
                    <span className="text-emerald-400 shrink-0 text-[10px]">
                      {g.chapterTitles.length} chap ({g.totalWords.toLocaleString()} từ)
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Auto download checkbox */}
            <div className="flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                id="auto-download"
                checked={autoDownloadEach}
                onChange={(e) => setAutoDownloadEach(e.target.checked)}
                className="w-4 h-4 rounded text-emerald-600 focus:ring-emerald-500 bg-neutral-800 border-neutral-700 cursor-pointer"
              />
              <label htmlFor="auto-download" className="text-neutral-300 cursor-pointer">
                Tự động tải file .{exportFormat.toUpperCase()} về máy ngay khi mỗi tập được gộp xong
              </label>
            </div>
          </div>
        )}

        {/* Single Chapter Export View */}
        {exportMode === 'single' && !isProcessing && (
          <div className="bg-neutral-800/40 border border-neutral-700/60 rounded-xl p-4 mb-4 space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-neutral-400">Chương xuất:</span>
              <span className="font-semibold text-neutral-200 truncate max-w-xs">
                {currentChapter?.title}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-400">Định dạng file:</span>
              <span className="text-emerald-400 font-bold font-mono">.{exportFormat.toUpperCase()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-400">Số từ:</span>
              <span className="font-mono text-neutral-200">
                {currentChapter?.content.trim().split(/\s+/).length.toLocaleString()} từ
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-400">Giọng đọc:</span>
              <span className="text-indigo-400 font-semibold">{voice}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-400">Tốc độ:</span>
              <span className="font-mono text-neutral-200">{speed}x</span>
            </div>
          </div>
        )}

        {/* Processing State (Sequential Queue Progress) */}
        {isProcessing && (
          <div className="space-y-4 py-3">
            <div className="p-4 rounded-xl bg-neutral-800/80 border border-neutral-700 space-y-3 text-xs">
              <div className="flex items-center justify-between text-neutral-300">
                <span className="font-semibold text-white flex items-center gap-2">
                  <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
                  {statusText}
                </span>
                {isPaused && (
                  <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold">
                    Đang tạm dừng
                  </span>
                )}
              </div>

              {/* Current File Progress */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] text-neutral-400">
                  <span>Tiến độ file hiện tại (Tập {currentGroupIndex + 1}):</span>
                  <span className="font-mono text-emerald-400 font-bold">{fileProgress}%</span>
                </div>
                <div className="w-full h-2 bg-neutral-900 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                    style={{ width: `${fileProgress}%` }}
                  />
                </div>
              </div>

              {/* Overall Progress */}
              <div className="space-y-1 pt-1 border-t border-neutral-700/50">
                <div className="flex justify-between text-[11px] text-neutral-400">
                  <span>
                    Tổng tiến trình toàn bộ ({currentGroupIndex + 1}/{plannedGroups.length} file .{exportFormat.toUpperCase()}):
                  </span>
                  <span className="font-mono text-indigo-400 font-bold">{overallProgress}%</span>
                </div>
                <div className="w-full h-2.5 bg-neutral-900 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-indigo-500 rounded-full transition-all duration-300"
                    style={{ width: `${overallProgress}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Action buttons during export: Pause / Resume / Cancel */}
            <div className="flex items-center justify-end gap-2 text-xs">
              <button
                onClick={handleTogglePause}
                className="px-3.5 py-1.5 rounded-lg border border-neutral-600 bg-neutral-800 text-neutral-200 hover:bg-neutral-700 transition-colors flex items-center gap-1.5"
              >
                {isPaused ? (
                  <>
                    <Play className="w-3.5 h-3.5 text-emerald-400" />
                    Tiếp tục
                  </>
                ) : (
                  <>
                    <Pause className="w-3.5 h-3.5 text-amber-400" />
                    Tạm dừng
                  </>
                )}
              </button>
              <button
                onClick={handleCancel}
                className="px-3.5 py-1.5 rounded-lg border border-rose-800 bg-rose-950/40 text-rose-300 hover:bg-rose-900/50 transition-colors"
              >
                Dừng hoàn toàn
              </button>
            </div>
          </div>
        )}

        {/* Completed files list */}
        {completedList.length > 0 && (
          <div className="mt-4 pt-3 border-t border-neutral-800 space-y-2">
            <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" />
              Các file âm thanh đã hoàn thành ({completedList.length}/{plannedGroups.length}):
            </span>
            <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
              {completedList.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-2 rounded-lg bg-emerald-950/20 border border-emerald-800/40 text-xs"
                >
                  <div className="flex items-center gap-2 truncate max-w-sm">
                    <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <span className="font-medium text-emerald-200 truncate">{item.name}</span>
                    <span className="text-[11px] text-neutral-400 font-mono">({item.sizeMb})</span>
                  </div>
                  <a
                    href={item.url}
                    download={item.name}
                    className="flex items-center gap-1 bg-emerald-700 hover:bg-emerald-600 text-white px-2.5 py-1 rounded text-[11px] font-medium transition-colors"
                  >
                    <Download className="w-3 h-3" />
                    Tải về .{item.format}
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Modal Footer */}
        <div className="mt-5 pt-3 border-t border-neutral-800 flex items-center justify-between">
          <div className="text-[11px] text-neutral-400">
            Giọng: <span className="text-neutral-200">{voice}</span> • Tốc độ: {speed}x • Định dạng:{' '}
            <span className="text-emerald-400 font-bold">.{exportFormat.toUpperCase()}</span>
          </div>

          <div className="flex items-center gap-2">
            {!isProcessing && (
              <>
                <button
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-medium text-neutral-400 hover:text-white transition-colors"
                >
                  Đóng
                </button>
                <button
                  onClick={handleStartExport}
                  disabled={plannedGroups.length === 0}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white px-5 py-2 rounded-xl font-medium text-xs shadow-md shadow-emerald-950 transition-all flex items-center gap-1.5"
                >
                  <Download className="w-4 h-4" />
                  Bắt đầu xuất .{exportFormat.toUpperCase()} ({plannedGroups.length} file)
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
