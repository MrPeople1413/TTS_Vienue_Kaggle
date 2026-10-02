import React from 'react';
import { BookOpen, Settings, CloudLightning, Plus, Headphones, Sparkles } from 'lucide-react';
import { Chapter, VoiceOption } from '../types';

interface HeaderProps {
  chapters: Chapter[];
  currentChapterId: string;
  onSelectChapter: (id: string) => void;
  activeTab: 'reader' | 'kaggle';
  setActiveTab: (tab: 'reader' | 'kaggle') => void;
  onOpenSettings: () => void;
  onOpenImport: () => void;
  voices: VoiceOption[];
  currentVoice: string;
  onSelectVoice: (voiceId: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  chapters,
  currentChapterId,
  onSelectChapter,
  activeTab,
  setActiveTab,
  onOpenSettings,
  onOpenImport,
  voices,
  currentVoice,
  onSelectVoice,
}) => {
  return (
    <header className="sticky top-0 z-30 bg-neutral-900/90 backdrop-blur-md border-b border-neutral-800 text-neutral-100">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Headphones className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-base tracking-tight text-white">Vietnamese TTS</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                v2.1 Web
              </span>
            </div>
            <p className="text-xs text-neutral-400">Đọc truyện tiếng Việt tự nhiên</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="hidden md:flex items-center p-1 bg-neutral-800/80 rounded-xl border border-neutral-700/60">
          <button
            onClick={() => setActiveTab('reader')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'reader'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            <BookOpen className="w-4 h-4" />
            Đọc Truyện
          </button>
          <button
            onClick={() => setActiveTab('kaggle')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'kaggle'
                ? 'bg-amber-600 text-white shadow-sm'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            <CloudLightning className="w-4 h-4" />
            Kaggle VieNeu Pipeline
          </button>
        </div>

        {/* Right Actions: Chapter Select, Voice Select, Import, Settings */}
        <div className="flex items-center gap-2">
          {activeTab === 'reader' && (
            <>
              {/* Chapter Selector */}
              <div className="relative max-w-[200px] sm:max-w-xs">
                <select
                  value={currentChapterId}
                  onChange={(e) => onSelectChapter(e.target.value)}
                  className="w-full truncate bg-neutral-800 border border-neutral-700 rounded-lg px-2.5 py-1.5 text-xs text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  title="Chọn chương truyện"
                >
                  {chapters.map((ch) => (
                    <option key={ch.id} value={ch.id}>
                      {ch.title}
                    </option>
                  ))}
                </select>
              </div>

              {/* Voice Quick Select */}
              <div className="hidden lg:block">
                <select
                  value={currentVoice}
                  onChange={(e) => onSelectVoice(e.target.value)}
                  className="bg-neutral-800/90 border border-neutral-700 rounded-lg px-2.5 py-1.5 text-xs text-neutral-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  title="Chọn giọng đọc"
                >
                  {voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Add Story / Chapter */}
              <button
                onClick={onOpenImport}
                className="flex items-center gap-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 px-3 py-1.5 rounded-lg text-xs font-medium border border-neutral-700 transition-colors"
                title="Tải file .txt hoặc thêm truyện mới"
              >
                <Plus className="w-3.5 h-3.5 text-indigo-400" />
                <span className="hidden sm:inline">Thêm truyện</span>
              </button>
            </>
          )}

          {/* Settings button */}
          <button
            onClick={onOpenSettings}
            className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors border border-neutral-800"
            title="Cài đặt hệ thống"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
