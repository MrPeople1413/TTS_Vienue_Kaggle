import React, { useState, useMemo } from 'react';
import { Chapter, AppSettings } from '../types';
import {
  CloudLightning,
  Download,
  Key,
  Database,
  Cpu,
  FileCode,
  CheckCircle2,
  AlertCircle,
  Copy,
  ExternalLink,
  Archive,
  Layers,
  Terminal,
  Disc,
  ArrowRight,
  FileText,
} from 'lucide-react';

interface KaggleBatchViewProps {
  chapters: Chapter[];
  settings: AppSettings;
  onSaveSettings: (newSettings: Partial<AppSettings>) => void;
}

function naturalCompare(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

export const KaggleBatchView: React.FC<KaggleBatchViewProps> = ({
  chapters,
  settings,
  onSaveSettings,
}) => {
  const [username, setUsername] = useState(settings.kaggle_username || '');
  const [apiKey, setApiKey] = useState(settings.kaggle_api_key || '');
  const [datasetSlug, setDatasetSlug] = useState(settings.kaggle_dataset_slug || 'viettt-tts-input');
  const [kernelSlug, setKernelSlug] = useState(settings.kaggle_kernel_slug || 'vieneu-tts-server');
  const [batchVoice, setBatchVoice] = useState(settings.kaggle_batch_voice || 'Ngọc Lan — nữ, giọng dịu dàng');
  const [batchSize, setBatchSize] = useState(settings.kaggle_batch_size || 10);
  const [exportFormat, setExportFormat] = useState<'wav' | 'mp3'>('wav');
  const [copiedCode, setCopiedCode] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isDownloadingZip, setIsDownloadingZip] = useState(false);

  // Sắp xếp tự nhiên các chương (chap1 ... chap100)
  const sortedChapters = useMemo(() => {
    return [...chapters].sort((a, b) => naturalCompare(a.title || a.id, b.title || b.id));
  }, [chapters]);

  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>(
    sortedChapters.map((c) => c.id)
  );

  const selectedChapters = useMemo(() => {
    return sortedChapters.filter((c) => selectedChapterIds.includes(c.id));
  }, [sortedChapters, selectedChapterIds]);

  const toggleSelectChapter = (id: string) => {
    setSelectedChapterIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleSaveConfig = () => {
    onSaveSettings({
      kaggle_username: username,
      kaggle_api_key: apiKey,
      kaggle_dataset_slug: datasetSlug,
      kaggle_kernel_slug: kernelSlug,
      kaggle_batch_voice: batchVoice,
      kaggle_batch_size: batchSize,
    });
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 3000);
  };

  // Tải gói input.zip thực tế từ backend server
  const handleDownloadRealInputZip = async () => {
    setIsDownloadingZip(true);
    try {
      const response = await fetch('/api/kaggle/export-zip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chapters: selectedChapters,
          voice: batchVoice,
          speed: settings.speed || 1.0,
          format: exportFormat,
          groupSize: batchSize,
          username: username || 'username',
          datasetSlug: datasetSlug || 'viettt-tts-input',
        }),
      });

      if (!response.ok) {
        throw new Error('Lỗi tạo gói ZIP');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `input.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Không thể tải gói input.zip: ${err.message}`);
    } finally {
      setIsDownloadingZip(false);
    }
  };

  // Tải file kết nối kaggle_connector.py
  const handleDownloadConnector = () => {
    const a = document.createElement('a');
    a.href = '/api/kaggle/connector-script';
    a.download = 'kaggle_connector.py';
    a.click();
  };

  // Tải file notebook kaggle_notebook_tts.py
  const handleDownloadNotebook = async () => {
    try {
      const res = await fetch('/api/kaggle/generate-notebook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          datasetSlug,
          voice: batchVoice,
          speed: settings.speed || 1.0,
          batchSize,
        }),
      });
      const data = await res.json();
      const blob = new Blob([data.pythonCode], { type: 'text/x-python' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'kaggle_notebook_tts.py';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Lỗi tải file notebook');
    }
  };

  // Preview of grouped files
  const groupedPreview = useMemo(() => {
    const groups: { name: string; count: number }[] = [];
    const effSize = Math.max(1, batchSize);
    for (let i = 0; i < selectedChapters.length; i += effSize) {
      const start = i + 1;
      const end = Math.min(i + effSize, selectedChapters.length);
      const padStart = String(start).padStart(3, '0');
      const padEnd = String(end).padStart(3, '0');
      groups.push({
        name: `Gop_Chuong_${padStart}_den_${padEnd}.${exportFormat}`,
        count: end - start + 1,
      });
    }
    return groups;
  }, [selectedChapters, batchSize, exportFormat]);

  const commandCli = `python kaggle_connector.py --group-size ${batchSize} --format ${exportFormat}`;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 pb-36 text-neutral-100">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-amber-950/70 via-neutral-900 to-indigo-950/70 border border-amber-500/30 rounded-2xl p-6 sm:p-8 mb-8 shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-3 rounded-2xl bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
              <CloudLightning className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
                  Kaggle VieNeu Pipeline Connector
                </h1>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  GPU T4 x2
                </span>
              </div>
              <p className="text-xs sm:text-sm text-neutral-400 mt-1">
                Tự động kết nối, đóng gói và gộp chương truyện (10 chương/file) trên GPU miễn phí của Kaggle
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadConnector}
              className="flex items-center gap-1.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white px-3.5 py-2 rounded-xl text-xs font-semibold shadow-md shadow-amber-950 transition-all"
              title="Tải file kết nối python"
            >
              <Download className="w-3.5 h-3.5" />
              Tải kaggle_connector.py
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Cấu hình Kaggle & Giọng đọc VieNeu */}
        <div className="space-y-6">
          <div className="bg-neutral-800/60 border border-neutral-700/60 rounded-2xl p-5">
            <h2 className="text-sm font-bold text-neutral-200 flex items-center gap-2 mb-4">
              <Key className="w-4 h-4 text-amber-400" />
              Thông tin cấu hình Kaggle
            </h2>

            <div className="space-y-3.5 text-xs">
              <div>
                <label className="block text-neutral-400 mb-1">Kaggle Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="ví dụ: mrpeople1413"
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="block text-neutral-400 mb-1">Kaggle API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Nhập Kaggle API Key..."
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="block text-neutral-400 mb-1">Tên Dataset Slug</label>
                <input
                  type="text"
                  value={datasetSlug}
                  onChange={(e) => setDatasetSlug(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-amber-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-neutral-400 mb-1">Giọng đọc VieNeu</label>
                <select
                  value={batchVoice}
                  onChange={(e) => setBatchVoice(e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  <option value="Ngọc Lan — nữ, giọng dịu dàng">Ngọc Lan — Nữ, dịu dàng, tự nhiên</option>
                  <option value="Bảo Long — nam, giọng truyền cảm">Bảo Long — Nam, hào hùng, trầm ấm</option>
                  <option value="Mai Phương — nữ, giọng miền Nam">Mai Phương — Nữ, miền Nam ngọt ngào</option>
                  <option value="custom::vn_despina_6">Voice Clone Custom (Despina v6)</option>
                </select>
              </div>

              {/* Định dạng xuất file */}
              <div>
                <label className="block text-neutral-400 mb-1">Định dạng file xuất</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setExportFormat('wav')}
                    className={`py-1.5 rounded-lg border text-center font-bold text-xs transition-colors ${
                      exportFormat === 'wav'
                        ? 'bg-amber-600 border-amber-500 text-white'
                        : 'bg-neutral-900 border-neutral-700 text-neutral-400'
                    }`}
                  >
                    .WAV (Chuẩn gốc)
                  </button>
                  <button
                    onClick={() => setExportFormat('mp3')}
                    className={`py-1.5 rounded-lg border text-center font-bold text-xs transition-colors ${
                      exportFormat === 'mp3'
                        ? 'bg-amber-600 border-amber-500 text-white'
                        : 'bg-neutral-900 border-neutral-700 text-neutral-400'
                    }`}
                  >
                    .MP3 (Nhẹ)
                  </button>
                </div>
              </div>

              {/* Tùy chọn gộp chương */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-neutral-400">Số chương gộp vào 1 file audio</label>
                  <span className="font-mono text-amber-400 font-bold">{batchSize} chap / file</span>
                </div>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={batchSize}
                  onChange={(e) => setBatchSize(Number(e.target.value) || 10)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-amber-500 font-mono"
                />
              </div>

              <button
                onClick={handleSaveConfig}
                className="w-full mt-2 bg-neutral-700 hover:bg-neutral-600 text-white font-medium py-2 rounded-lg transition-colors flex items-center justify-center gap-1.5 shadow-sm"
              >
                {saveSuccess ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    Đã lưu cấu hình!
                  </>
                ) : (
                  'Lưu cấu hình'
                )}
              </button>
            </div>
          </div>

          {/* Quick Hardware Info */}
          <div className="bg-neutral-800/40 border border-neutral-700/40 rounded-2xl p-5 text-xs space-y-2.5">
            <h3 className="font-semibold text-neutral-200 flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-indigo-400" />
              Sức mạnh Dual GPU T4 x2
            </h3>
            <p className="text-neutral-400 leading-relaxed">
              Kaggle cấp 30 giờ GPU T4 x2 mỗi tuần miễn phí. Script kết nối mới này tự động chia tải lên cả 2 GPU song song, xử lý 100 chương truyện dài chỉ trong thời gian ngắn mà không làm nóng hay tốn RAM máy tính của bạn.
            </p>
          </div>
        </div>

        {/* Right Column: Chọn chương, Xem trước & 2 Phương thức kết nối */}
        <div className="lg:col-span-2 space-y-6">
          {/* Chapter selection & grouping preview */}
          <div className="bg-neutral-800/60 border border-neutral-700/60 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-neutral-200 flex items-center gap-2">
                <Database className="w-4 h-4 text-amber-400" />
                Chọn chương truyện đóng gói ({selectedChapters.length}/{sortedChapters.length})
              </h2>
              <div className="flex items-center gap-2 text-xs">
                <button
                  onClick={() =>
                    setSelectedChapterIds(
                      selectedChapterIds.length === sortedChapters.length
                        ? []
                        : sortedChapters.map((c) => c.id)
                    )
                  }
                  className="text-amber-400 hover:underline"
                >
                  {selectedChapterIds.length === sortedChapters.length ? 'Bỏ chọn hết' : 'Chọn tất cả'}
                </button>
              </div>
            </div>

            <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
              {sortedChapters.map((chap, i) => {
                const isSelected = selectedChapterIds.includes(chap.id);
                return (
                  <div
                    key={chap.id}
                    onClick={() => toggleSelectChapter(chap.id)}
                    className={`flex items-center justify-between p-2 rounded-xl border text-xs cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-amber-950/30 border-amber-700/60 text-amber-200'
                        : 'bg-neutral-900/50 border-neutral-800 text-neutral-400 hover:border-neutral-700'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate max-w-md">
                      <span className="w-6 h-5 rounded bg-black/40 text-amber-400 font-mono text-[10px] flex items-center justify-center shrink-0">
                        #{i + 1}
                      </span>
                      <span className="truncate font-medium">{chap.title}</span>
                    </div>
                    <span className="font-mono text-[11px] opacity-75">
                      {chap.content.trim().split(/\s+/).length.toLocaleString()} từ
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Preview of grouped output */}
            <div className="mt-3 pt-3 border-t border-neutral-700/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-neutral-400">
              <span className="flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-amber-400" />
                Dự kiến tạo: <b className="text-white">{groupedPreview.length} file .{exportFormat.toUpperCase()}</b> ({batchSize} chap/file)
              </span>
              <button
                onClick={handleDownloadRealInputZip}
                disabled={selectedChapters.length === 0 || isDownloadingZip}
                className="flex items-center gap-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow-sm transition-all"
              >
                <Archive className="w-3.5 h-3.5" />
                {isDownloadingZip ? 'Đang nén input.zip...' : `Tải gói input.zip (${selectedChapters.length} chap)`}
              </button>
            </div>
          </div>

          {/* Phương thức 1: Kết nối tự động qua file script */}
          <div className="bg-neutral-800/60 border border-amber-500/30 rounded-2xl p-5 relative overflow-hidden">
            <div className="absolute top-0 right-0 bg-amber-500/20 text-amber-300 border-l border-b border-amber-500/30 px-3 py-1 rounded-bl-xl text-[11px] font-bold">
              Cách 1: Tự Động Hoàn Toàn (Khuyến nghị)
            </div>

            <div className="flex items-center gap-2 mb-2">
              <Terminal className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-bold text-white">
                Chạy file kết nối `kaggle_connector.py`
              </h3>
            </div>
            <p className="text-xs text-neutral-400 mb-3">
              Chỉ cần chạy 1 dòng lệnh, script sẽ tự động lấy truyện từ web app, đẩy lên Kaggle, kích hoạt GPU T4 x2 và tự tải các file audio hoàn chỉnh về thư mục <code className="text-amber-300">output_audio/</code>.
            </p>

            <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-3 flex items-center justify-between gap-2 font-mono text-xs text-amber-300 mb-3">
              <span className="truncate">{commandCli}</span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(commandCli);
                  setCopiedCmd(true);
                  setTimeout(() => setCopiedCmd(false), 2000);
                }}
                className="bg-neutral-800 hover:bg-neutral-700 text-neutral-200 px-2 py-1 rounded text-[11px] font-sans transition-colors shrink-0"
              >
                {copiedCmd ? 'Đã sao chép!' : 'Sao chép lệnh'}
              </button>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-neutral-700/40 text-xs">
              <span className="text-neutral-400">File kết nối đã được thiết kế sẵn trong thư mục gốc.</span>
              <button
                onClick={handleDownloadConnector}
                className="flex items-center gap-1 text-amber-400 hover:text-amber-300 hover:underline font-semibold"
              >
                <Download className="w-3.5 h-3.5" />
                Tải lại file `kaggle_connector.py`
              </button>
            </div>
          </div>

          {/* Phương thức 2: Chạy trực tiếp trên giao diện web Kaggle */}
          <div className="bg-neutral-800/60 border border-neutral-700/60 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-white">
                  Cách 2: Chạy thủ công trên Kaggle Notebooks
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDownloadNotebook}
                  className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 text-white px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  Tải .py
                </button>
                <a
                  href="https://www.kaggle.com/code"
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 px-2.5 py-1 rounded-lg text-xs transition-colors"
                >
                  Mở Kaggle
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>

            <div className="space-y-2 text-xs text-neutral-300 bg-neutral-900/60 p-3 rounded-xl border border-neutral-800">
              <div className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-[11px] shrink-0">1</span>
                <span>Tải file <b>input.zip</b> ở trên rồi tải lên Kaggle thành 1 Dataset mới (ví dụ đặt tên <code>viettt-tts-input</code>).</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-[11px] shrink-0">2</span>
                <span>Tạo Notebook mới trên Kaggle, chọn <b>Settings → Accelerator → GPU T4 x2</b> và Add Dataset vừa tạo.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-[11px] shrink-0">3</span>
                <span>Dán mã từ file <b>kaggle_notebook_tts.py</b> và nhấn <b>Run All</b>. Sau khi xong, tải file <code>output.zip</code> tại mục Output!</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
