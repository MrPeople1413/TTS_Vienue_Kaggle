import React from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  RotateCw,
  Volume2,
  VolumeX,
  Download,
  ListRestart,
  Gauge,
  Sparkles,
  Loader2,
} from 'lucide-react';

interface PlayerBarProps {
  isPlaying: boolean;
  isLoadingAudio: boolean;
  onTogglePlay: () => void;
  onPrevChunk: () => void;
  onNextChunk: () => void;
  onSkipBack5: () => void;
  onSkipForward5: () => void;
  currentChunkIndex: number;
  totalChunks: number;
  onSeekChunk: (index: number) => void;
  speed: number;
  onChangeSpeed: (speed: number) => void;
  volume: number;
  onChangeVolume: (volume: number) => void;
  autoNext: boolean;
  onToggleAutoNext: () => void;
  onOpenExportModal: () => void;
  currentVoiceName: string;
}

const SPEED_OPTIONS = [0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0];

export const PlayerBar: React.FC<PlayerBarProps> = ({
  isPlaying,
  isLoadingAudio,
  onTogglePlay,
  onPrevChunk,
  onNextChunk,
  onSkipBack5,
  onSkipForward5,
  currentChunkIndex,
  totalChunks,
  onSeekChunk,
  speed,
  onChangeSpeed,
  volume,
  onChangeVolume,
  autoNext,
  onToggleAutoNext,
  onOpenExportModal,
  currentVoiceName,
}) => {
  const [showSpeedMenu, setShowSpeedMenu] = React.useState(false);
  const [isMuted, setIsMuted] = React.useState(false);
  const prevVolumeRef = React.useRef(volume);

  const toggleMute = () => {
    if (isMuted) {
      onChangeVolume(prevVolumeRef.current || 0.85);
      setIsMuted(false);
    } else {
      prevVolumeRef.current = volume;
      onChangeVolume(0);
      setIsMuted(true);
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-neutral-900/95 backdrop-blur-md border-t border-neutral-800 text-neutral-100 shadow-2xl">
      {/* Progress Slider on top edge */}
      <div className="relative w-full h-1.5 bg-neutral-800 hover:h-2.5 transition-all cursor-pointer group">
        <input
          type="range"
          min={0}
          max={Math.max(0, totalChunks - 1)}
          value={currentChunkIndex}
          onChange={(e) => onSeekChunk(Number(e.target.value))}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
        />
        <div
          className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 group-hover:from-indigo-400 group-hover:to-violet-400 transition-all"
          style={{
            width: totalChunks > 0 ? `${((currentChunkIndex + 1) / totalChunks) * 100}%` : '0%',
          }}
        />
      </div>

      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-col md:flex-row items-center justify-between gap-3">
        {/* Left: Info & Voice */}
        <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-start">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-neutral-200 truncate max-w-[200px]">
                {currentVoiceName}
              </span>
              <span className="text-[11px] text-neutral-400 font-mono">
                Đoạn {totalChunks > 0 ? currentChunkIndex + 1 : 0} / {totalChunks}
              </span>
            </div>
          </div>

          {/* Quick Auto Next Chapter toggle */}
          <button
            onClick={onToggleAutoNext}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors border ${
              autoNext
                ? 'bg-indigo-950/60 border-indigo-700/80 text-indigo-300'
                : 'bg-neutral-800 border-neutral-700 text-neutral-400'
            }`}
            title="Tự động chuyển chương khi đọc hết"
          >
            <ListRestart className="w-3 h-3" />
            <span>Tự chuyển chap: {autoNext ? 'Bật' : 'Tắt'}</span>
          </button>
        </div>

        {/* Center: Playback Controls */}
        <div className="flex items-center gap-2 sm:gap-4">
          {/* Skip -5 chunks */}
          <button
            onClick={onSkipBack5}
            disabled={currentChunkIndex <= 0}
            className="p-2 text-neutral-400 hover:text-white disabled:opacity-30 disabled:hover:text-neutral-400 transition-colors"
            title="Lùi lại 5 đoạn"
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          {/* Previous chunk */}
          <button
            onClick={onPrevChunk}
            disabled={currentChunkIndex <= 0}
            className="p-2 text-neutral-300 hover:text-white disabled:opacity-30 disabled:hover:text-neutral-300 transition-colors"
            title="Đoạn trước đó"
          >
            <SkipBack className="w-5 h-5" />
          </button>

          {/* Main Play / Pause Button */}
          <button
            onClick={onTogglePlay}
            disabled={totalChunks === 0}
            className="w-12 h-12 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center shadow-lg shadow-indigo-600/30 transition-transform active:scale-95 disabled:opacity-50"
            title={isPlaying ? 'Tạm dừng (Space)' : 'Phát tiếp (Space)'}
          >
            {isLoadingAudio ? (
              <Loader2 className="w-6 h-6 animate-spin" />
            ) : isPlaying ? (
              <Pause className="w-6 h-6 fill-current" />
            ) : (
              <Play className="w-6 h-6 fill-current ml-0.5" />
            )}
          </button>

          {/* Next chunk */}
          <button
            onClick={onNextChunk}
            disabled={currentChunkIndex >= totalChunks - 1}
            className="p-2 text-neutral-300 hover:text-white disabled:opacity-30 disabled:hover:text-neutral-300 transition-colors"
            title="Đoạn kế tiếp"
          >
            <SkipForward className="w-5 h-5" />
          </button>

          {/* Skip +5 chunks */}
          <button
            onClick={onSkipForward5}
            disabled={currentChunkIndex >= totalChunks - 1}
            className="p-2 text-neutral-400 hover:text-white disabled:opacity-30 disabled:hover:text-neutral-400 transition-colors"
            title="Tiến lên 5 đoạn"
          >
            <RotateCw className="w-4 h-4" />
          </button>
        </div>

        {/* Right: Speed, Volume & Export Audio */}
        <div className="flex items-center gap-3 w-full md:w-auto justify-end">
          {/* Speed Selector */}
          <div className="relative">
            <button
              onClick={() => setShowSpeedMenu(!showSpeedMenu)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs font-mono font-medium text-neutral-200 border border-neutral-700 transition-colors"
              title="Tốc độ đọc"
            >
              <Gauge className="w-3.5 h-3.5 text-indigo-400" />
              <span>{speed}x</span>
            </button>

            {showSpeedMenu && (
              <div className="absolute bottom-full mb-2 right-0 bg-neutral-800 border border-neutral-700 rounded-xl p-1.5 shadow-xl grid grid-cols-2 gap-1 z-50 min-w-[130px]">
                {SPEED_OPTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      onChangeSpeed(s);
                      setShowSpeedMenu(false);
                    }}
                    className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors text-left ${
                      speed === s
                        ? 'bg-indigo-600 text-white font-semibold'
                        : 'text-neutral-300 hover:bg-neutral-700'
                    }`}
                  >
                    {s}x
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Volume Control */}
          <div className="hidden sm:flex items-center gap-2">
            <button
              onClick={toggleMute}
              className="p-1.5 text-neutral-400 hover:text-white transition-colors"
              title={isMuted ? 'Bật âm lượng' : 'Tắt tiếng'}
            >
              {isMuted || volume === 0 ? (
                <VolumeX className="w-4 h-4 text-rose-400" />
              ) : (
                <Volume2 className="w-4 h-4" />
              )}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={volume}
              onChange={(e) => {
                onChangeVolume(Number(e.target.value));
                if (isMuted) setIsMuted(false);
              }}
              className="w-16 h-1.5 bg-neutral-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              title={`Âm lượng: ${Math.round(volume * 100)}%`}
            />
          </div>

          {/* Export Audio (MP3 / WAV) Button */}
          <button
            onClick={onOpenExportModal}
            className="flex items-center gap-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow-md shadow-emerald-950 transition-all active:scale-95"
            title="Xuất file âm thanh MP3 / WAV (hỗ trợ gộp nhiều chương)"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Xuất Audio</span>
          </button>
        </div>
      </div>
    </div>
  );
};
