import React from 'react';
import { X, Sliders, Moon, Sun, Check, Volume2, Sparkles, BookOpen } from 'lucide-react';
import { AppSettings, VoiceOption } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: AppSettings;
  onUpdateSettings: (newSettings: Partial<AppSettings>) => void;
  voices: VoiceOption[];
  theme: 'dark' | 'black' | 'sepia' | 'light';
  onChangeTheme: (theme: 'dark' | 'black' | 'sepia' | 'light') => void;
  fontSize: 'sm' | 'base' | 'lg' | 'xl';
  onChangeFontSize: (size: 'sm' | 'base' | 'lg' | 'xl') => void;
  fontFamily: 'serif' | 'sans';
  onChangeFontFamily: (family: 'serif' | 'sans') => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onUpdateSettings,
  voices,
  theme,
  onChangeTheme,
  fontSize,
  onChangeFontSize,
  fontFamily,
  onChangeFontFamily,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl max-w-lg w-full p-6 text-neutral-100 shadow-2xl overflow-y-auto max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-neutral-800 mb-5">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Cài đặt ứng dụng</h2>
              <p className="text-xs text-neutral-400">Tùy biến giọng đọc, kích thước văn bản và giao diện</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-neutral-400 hover:text-white rounded-lg hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-5 text-xs">
          {/* TTS Engine & Voice */}
          <div className="space-y-3">
            <h3 className="font-semibold text-neutral-300 text-sm flex items-center gap-1.5">
              <Volume2 className="w-4 h-4 text-indigo-400" />
              Công nghệ TTS & Giọng đọc
            </h3>

            <div>
              <label className="block text-neutral-400 mb-1">Giọng đọc mặc định</label>
              <select
                value={settings.edge_voice}
                onChange={(e) => onUpdateSettings({ edge_voice: e.target.value })}
                className="w-full bg-neutral-800 border border-neutral-700 rounded-xl px-3 py-2 text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Chunk Size */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-neutral-400">Độ dài mỗi đoạn đọc (Chunk Size)</label>
                <span className="font-mono text-indigo-400 font-semibold">{settings.chunk_size || 180} ký tự</span>
              </div>
              <input
                type="range"
                min={100}
                max={300}
                step={10}
                value={settings.chunk_size || 180}
                onChange={(e) => onUpdateSettings({ chunk_size: Number(e.target.value) })}
                className="w-full h-1.5 bg-neutral-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <p className="text-[11px] text-neutral-500 mt-1">
                Khuyến nghị 180 ký tự để ngắt câu tự nhiên theo ngữ cảnh tiếng Việt và không bị trễ âm thanh.
              </p>
            </div>

            {/* Cache Toggle */}
            <div className="flex items-center justify-between p-3 rounded-xl bg-neutral-800/40 border border-neutral-700/50">
              <div>
                <span className="font-medium text-neutral-200">Lưu đệm âm thanh (Audio Cache)</span>
                <p className="text-[11px] text-neutral-400">Tăng tốc độ đọc khi nghe lại các đoạn văn đã phát</p>
              </div>
              <button
                onClick={() => onUpdateSettings({ use_cache: !settings.use_cache })}
                className={`w-11 h-6 rounded-full transition-colors relative flex items-center px-0.5 ${
                  settings.use_cache ? 'bg-indigo-600' : 'bg-neutral-700'
                }`}
              >
                <span
                  className={`w-5 h-5 rounded-full bg-white transition-transform ${
                    settings.use_cache ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Reader Interface */}
          <div className="pt-4 border-t border-neutral-800 space-y-3">
            <h3 className="font-semibold text-neutral-300 text-sm flex items-center gap-1.5">
              <BookOpen className="w-4 h-4 text-indigo-400" />
              Giao diện đọc truyện
            </h3>

            {/* Theme options */}
            <div>
              <label className="block text-neutral-400 mb-2">Chủ đề màu sắc</label>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { id: 'dark', name: 'Đêm tối', bg: 'bg-neutral-900 border-neutral-700 text-white' },
                  { id: 'black', name: 'Đen OLED', bg: 'bg-black border-neutral-800 text-neutral-200' },
                  { id: 'sepia', name: 'Giấy ấm', bg: 'bg-[#f7f1e5] border-[#dfd5be] text-[#3d3228]' },
                  { id: 'light', name: 'Sáng', bg: 'bg-white border-neutral-300 text-neutral-900' },
                ].map((th) => (
                  <button
                    key={th.id}
                    onClick={() => onChangeTheme(th.id as any)}
                    className={`p-2.5 rounded-xl border text-center font-medium transition-all ${th.bg} ${
                      theme === th.id ? 'ring-2 ring-indigo-500 scale-[1.02]' : 'opacity-70 hover:opacity-100'
                    }`}
                  >
                    <span className="text-xs">{th.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Font size */}
            <div>
              <label className="block text-neutral-400 mb-2">Cỡ chữ hiển thị</label>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { id: 'sm', label: 'Nhỏ' },
                  { id: 'base', label: 'Vừa' },
                  { id: 'lg', label: 'Lớn' },
                  { id: 'xl', label: 'Rất lớn' },
                ].map((sz) => (
                  <button
                    key={sz.id}
                    onClick={() => onChangeFontSize(sz.id as any)}
                    className={`py-2 rounded-xl border text-center transition-colors ${
                      fontSize === sz.id
                        ? 'bg-indigo-600 border-indigo-500 text-white font-semibold'
                        : 'bg-neutral-800 border-neutral-700 text-neutral-300 hover:bg-neutral-700'
                    }`}
                  >
                    {sz.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Font family */}
            <div>
              <label className="block text-neutral-400 mb-2">Kiểu phông chữ</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => onChangeFontFamily('serif')}
                  className={`p-2.5 rounded-xl border text-center transition-colors font-reader-serif ${
                    fontFamily === 'serif'
                      ? 'bg-indigo-600 border-indigo-500 text-white font-bold'
                      : 'bg-neutral-800 border-neutral-700 text-neutral-300 hover:bg-neutral-700'
                  }`}
                >
                  Merriweather (Có chân / Sách)
                </button>
                <button
                  onClick={() => onChangeFontFamily('sans')}
                  className={`p-2.5 rounded-xl border text-center transition-colors font-reader-sans ${
                    fontFamily === 'sans'
                      ? 'bg-indigo-600 border-indigo-500 text-white font-bold'
                      : 'bg-neutral-800 border-neutral-700 text-neutral-300 hover:bg-neutral-700'
                  }`}
                >
                  Plus Jakarta (Không chân / Hiện đại)
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-neutral-800 flex justify-end">
          <button
            onClick={onClose}
            className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2 rounded-xl font-medium text-xs shadow-md shadow-indigo-600/30 transition-colors"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
};
