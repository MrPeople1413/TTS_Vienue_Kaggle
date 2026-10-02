import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Chapter, AppSettings, VoiceOption, ReadingPosition } from './types';
import { splitIntoChunks, TextChunk } from './utils/textChunker';
import { Header } from './components/Header';
import { ReaderView } from './components/ReaderView';
import { PlayerBar } from './components/PlayerBar';
import { KaggleBatchView } from './components/KaggleBatchView';
import { SettingsModal } from './components/SettingsModal';
import { ImportModal } from './components/ImportModal';
import { ExportModal } from './components/ExportModal';

export const App: React.FC = () => {
  // App State
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [currentChapterId, setCurrentChapterId] = useState<string>('');
  const [currentChunkIndex, setCurrentChunkIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLoadingAudio, setIsLoadingAudio] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'reader' | 'kaggle'>('reader');

  // Modals
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);

  // Settings
  const [settings, setSettings] = useState<AppSettings>({
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
    kaggle_username: '',
    kaggle_api_key: '',
    kaggle_dataset_slug: 'viettt-tts-input',
    kaggle_kernel_slug: 'mrpeople1413/vieneu-tts-server',
    kaggle_batch_voice: 'Ngọc Lan — nữ, giọng dịu dàng',
    kaggle_batch_size: 10,
    kaggle_poll_sec: 40,
  });

  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [theme, setTheme] = useState<'dark' | 'black' | 'sepia' | 'light'>('dark');
  const [fontSize, setFontSize] = useState<'sm' | 'base' | 'lg' | 'xl'>('base');
  const [fontFamily, setFontFamily] = useState<'serif' | 'sans'>('sans');

  // Audio elements, Refs & Cache
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef<boolean>(false);
  const settingsRef = useRef<AppSettings>(settings);
  const playRequestIdRef = useRef<number>(0);
  const playChunkRef = useRef<((index: number, forcedVoice?: string) => Promise<void>) | null>(null);
  const audioCache = useRef<Map<string, string>>(new Map());

  // Always keep settingsRef in sync with latest settings
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  // Keep isPlayingRef in sync
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  // Initialize Audio Object
  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;
    return () => {
      audio.pause();
      audio.src = '';
      audioRef.current = null;
    };
  }, []);

  // Fetch initial data: chapters, settings, positions, voices
  useEffect(() => {
    // 1. Stories
    fetch('/api/stories')
      .then((res) => res.json())
      .then((data: Chapter[]) => {
        setChapters(data);
        if (data.length > 0) {
          fetch('/api/positions')
            .then((r) => r.json())
            .then((positions: Record<string, any>) => {
              const savedLastId = positions._lastChapterId;
              const targetChap = data.find((c) => c.id === savedLastId) || data[0];
              setCurrentChapterId(targetChap.id);
              if (positions[targetChap.id]?.chunkIndex != null) {
                setCurrentChunkIndex(positions[targetChap.id].chunkIndex);
              }
            })
            .catch(() => {
              setCurrentChapterId(data[0].id);
            });
        }
      })
      .catch((err) => console.error('Failed to load stories:', err));

    // 2. Settings
    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => {
        setSettings((prev) => {
          const merged = { ...prev, ...data };
          settingsRef.current = merged;
          return merged;
        });
      })
      .catch((err) => console.error('Failed to load settings:', err));

    // 3. Voices
    fetch('/api/voices')
      .then((res) => res.json())
      .then((data: VoiceOption[]) => setVoices(data))
      .catch((err) => console.error('Failed to load voices:', err));
  }, []);

  // Find active chapter
  const currentChapter = useMemo(() => {
    return chapters.find((c) => c.id === currentChapterId) || chapters[0] || null;
  }, [chapters, currentChapterId]);

  // Compute text chunks for current chapter
  const currentChunks = useMemo(() => {
    if (!currentChapter) return [];
    return splitIntoChunks(currentChapter.content, settings.chunk_size || 180);
  }, [currentChapter, settings.chunk_size]);

  // Ensure currentChunkIndex is within bounds
  useEffect(() => {
    if (currentChunks.length > 0 && currentChunkIndex >= currentChunks.length) {
      setCurrentChunkIndex(0);
    }
  }, [currentChunks.length, currentChunkIndex]);

  // Auto-save reading position
  useEffect(() => {
    if (!currentChapterId) return;
    const posPayload = {
      _lastChapterId: currentChapterId,
      [currentChapterId]: {
        chunkIndex: currentChunkIndex,
        updatedAt: Date.now(),
      },
    };
    fetch('/api/positions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(posPayload),
    }).catch(() => {});
  }, [currentChapterId, currentChunkIndex]);

  // Browser speech fallback
  const fallbackBrowserSpeech = (text: string, index: number) => {
    setIsLoadingAudio(false);
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'vi-VN';
      utterance.rate = settingsRef.current.speed;
      utterance.volume = settingsRef.current.volume;

      utterance.onend = () => {
        if (!isPlayingRef.current) return;
        if (index + 1 < currentChunks.length) {
          playChunkRef.current?.(index + 1);
        } else if (settingsRef.current.auto_next) {
          handleNextChapter(true);
        } else {
          setIsPlaying(false);
        }
      };

      utterance.onerror = () => {
        setIsPlaying(false);
      };

      window.speechSynthesis.speak(utterance);
    } else {
      setIsPlaying(false);
    }
  };

  // Play audio for a specific chunk index (always fresh voice & settings)
  const playChunk = async (index: number, forcedVoice?: string) => {
    if (!currentChunks[index]) return;

    // Track request ID to ignore stale network responses
    const reqId = ++playRequestIdRef.current;

    setCurrentChunkIndex(index);
    setIsLoadingAudio(true);
    setIsPlaying(true);

    const activeVoice = forcedVoice || settingsRef.current.edge_voice;
    const activeSpeed = settingsRef.current.speed;
    const activeVolume = settingsRef.current.volume;
    const activeUseCache = settingsRef.current.use_cache;
    const chunk = currentChunks[index];
    const cacheKey = `${activeVoice}:${activeSpeed}:${chunk.text}`;

    try {
      let audioUrl = audioCache.current.get(cacheKey);

      if (!audioUrl) {
        const res = await fetch('/api/tts/synthesize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: chunk.text,
            voice: activeVoice,
            speed: activeSpeed,
            useCache: activeUseCache,
          }),
        });

        // If another request started while waiting, drop this result
        if (playRequestIdRef.current !== reqId) {
          return;
        }

        if (!res.ok) {
          throw new Error('TTS server error');
        }

        const blob = await res.blob();
        audioUrl = URL.createObjectURL(blob);
        audioCache.current.set(cacheKey, audioUrl);
      }

      // Check request ID again
      if (playRequestIdRef.current !== reqId) {
        return;
      }

      if (!audioRef.current) {
        audioRef.current = new Audio();
      }

      const audio = audioRef.current;
      audio.pause();
      audio.src = audioUrl;
      audio.playbackRate = 1.0;
      audio.volume = activeVolume;

      audio.onended = () => {
        if (!isPlayingRef.current) return;
        if (index + 1 < currentChunks.length) {
          playChunkRef.current?.(index + 1);
        } else {
          // Reached end of chapter
          if (settingsRef.current.auto_next) {
            handleNextChapter(true);
          } else {
            setIsPlaying(false);
          }
        }
      };

      audio.onerror = (e) => {
        if (playRequestIdRef.current !== reqId) return;
        console.warn('Audio playback error, falling back to browser speech:', e);
        fallbackBrowserSpeech(chunk.text, index);
      };

      await audio.play();
      if (playRequestIdRef.current === reqId) {
        setIsLoadingAudio(false);
      }

      // Preload next chunk with the CURRENT active voice
      if (index + 1 < currentChunks.length) {
        const nextChunk = currentChunks[index + 1];
        const nextKey = `${activeVoice}:${activeSpeed}:${nextChunk.text}`;
        if (!audioCache.current.has(nextKey)) {
          fetch('/api/tts/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              text: nextChunk.text,
              voice: activeVoice,
              speed: activeSpeed,
              useCache: activeUseCache,
            }),
          })
            .then((r) => r.blob())
            .then((b) => {
              audioCache.current.set(nextKey, URL.createObjectURL(b));
            })
            .catch(() => {});
        }
      }
    } catch (err) {
      if (playRequestIdRef.current !== reqId) return;
      console.warn('Falling back to browser speech synthesis:', err);
      fallbackBrowserSpeech(chunk.text, index);
    }
  };

  // Keep playChunkRef updated
  useEffect(() => {
    playChunkRef.current = playChunk;
  });

  // Dedicated instant voice switch handler
  const handleVoiceChange = (newVoiceId: string) => {
    // 1. Immediately update ref & state
    settingsRef.current.edge_voice = newVoiceId;
    handleUpdateSettings({ edge_voice: newVoiceId });

    // 2. Invalidate pending network requests
    playRequestIdRef.current++;

    // 3. Stop any current audio immediately
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current.src = '';
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }

    // 4. If playing, instantly restart the current sentence in the NEW voice!
    if (isPlayingRef.current) {
      setIsLoadingAudio(true);
      setTimeout(() => {
        playChunk(currentChunkIndex, newVoiceId);
      }, 50);
    }
  };

  // Play / Pause toggle
  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      playRequestIdRef.current++;
      if (audioRef.current) audioRef.current.pause();
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    } else {
      playChunk(currentChunkIndex);
    }
  };

  // Chapter navigation
  const currentChapterIndex = chapters.findIndex((c) => c.id === currentChapterId);
  const hasPrevChapter = currentChapterIndex > 0;
  const hasNextChapter = currentChapterIndex < chapters.length - 1;

  const handlePrevChapter = () => {
    if (hasPrevChapter) {
      const prevId = chapters[currentChapterIndex - 1].id;
      setCurrentChapterId(prevId);
      setCurrentChunkIndex(0);
      if (isPlaying) {
        if (audioRef.current) audioRef.current.pause();
        setTimeout(() => playChunk(0), 100);
      }
    }
  };

  const handleNextChapter = (autoStart = false) => {
    if (hasNextChapter) {
      const nextId = chapters[currentChapterIndex + 1].id;
      setCurrentChapterId(nextId);
      setCurrentChunkIndex(0);
      if (isPlaying || autoStart) {
        if (audioRef.current) audioRef.current.pause();
        setTimeout(() => playChunk(0), 100);
      }
    } else {
      setIsPlaying(false);
    }
  };

  // Chunk skips
  const handlePrevChunk = () => {
    if (currentChunkIndex > 0) {
      const target = currentChunkIndex - 1;
      if (isPlaying) playChunk(target);
      else setCurrentChunkIndex(target);
    }
  };

  const handleNextChunk = () => {
    if (currentChunkIndex < currentChunks.length - 1) {
      const target = currentChunkIndex + 1;
      if (isPlaying) playChunk(target);
      else setCurrentChunkIndex(target);
    }
  };

  const handleSkipBack5 = () => {
    const target = Math.max(0, currentChunkIndex - 5);
    if (isPlaying) playChunk(target);
    else setCurrentChunkIndex(target);
  };

  const handleSkipForward5 = () => {
    const target = Math.min(currentChunks.length - 1, currentChunkIndex + 5);
    if (isPlaying) playChunk(target);
    else setCurrentChunkIndex(target);
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }

      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        handlePrevChunk();
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        handleNextChunk();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isPlaying, currentChunkIndex, currentChunks.length]);

  // Update Settings
  const handleUpdateSettings = (newSettings: Partial<AppSettings>) => {
    setSettings((prev) => {
      const updated = { ...prev, ...newSettings };
      settingsRef.current = updated;
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
      }).catch(() => {});
      return updated;
    });

    if (newSettings.volume != null && audioRef.current) {
      audioRef.current.volume = newSettings.volume;
    }
  };

  // Add Chapters from import
  const handleAddChapters = (newChaps: Chapter[]) => {
    setChapters((prev) => [...prev, ...newChaps]);
    if (newChaps.length > 0) {
      setCurrentChapterId(newChaps[0].id);
      setCurrentChunkIndex(0);
    }
  };

  const currentVoiceObj = voices.find((v) => v.id === settings.edge_voice);
  const currentVoiceName = currentVoiceObj ? currentVoiceObj.name : 'Hoài My Neural (Nữ)';

  return (
    <div className="min-h-screen flex flex-col bg-neutral-900 text-neutral-100">
      {/* Top Navbar */}
      <Header
        chapters={chapters}
        currentChapterId={currentChapterId}
        onSelectChapter={(id) => {
          if (audioRef.current) audioRef.current.pause();
          setCurrentChapterId(id);
          setCurrentChunkIndex(0);
          setIsPlaying(false);
        }}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenImport={() => setIsImportOpen(true)}
        voices={voices}
        currentVoice={settings.edge_voice}
        onSelectVoice={handleVoiceChange}
      />

      {/* Main Content View */}
      <main className="flex-1">
        {activeTab === 'reader' ? (
          currentChapter ? (
            <ReaderView
              chapter={currentChapter}
              chunks={currentChunks}
              currentChunkIndex={currentChunkIndex}
              isPlaying={isPlaying}
              onPlayChunk={(idx) => playChunk(idx)}
              onPrevChapter={handlePrevChapter}
              onNextChapter={() => handleNextChapter()}
              hasPrevChapter={hasPrevChapter}
              hasNextChapter={hasNextChapter}
              theme={theme}
              fontSize={fontSize}
              fontFamily={fontFamily}
            />
          ) : (
            <div className="flex flex-col items-center justify-center py-24 text-center px-4">
              <p className="text-neutral-400 mb-4">Không có chương truyện nào để hiển thị.</p>
              <button
                onClick={() => setIsImportOpen(true)}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl font-medium text-sm transition-colors"
              >
                Thêm truyện ngay
              </button>
            </div>
          )
        ) : (
          <KaggleBatchView
            chapters={chapters}
            settings={settings}
            onSaveSettings={handleUpdateSettings}
          />
        )}
      </main>

      {/* Persistent Bottom Player Bar */}
      {currentChapter && (
        <PlayerBar
          isPlaying={isPlaying}
          isLoadingAudio={isLoadingAudio}
          onTogglePlay={togglePlay}
          onPrevChunk={handlePrevChunk}
          onNextChunk={handleNextChunk}
          onSkipBack5={handleSkipBack5}
          onSkipForward5={handleSkipForward5}
          currentChunkIndex={currentChunkIndex}
          totalChunks={currentChunks.length}
          onSeekChunk={(idx) => {
            if (isPlaying) playChunk(idx);
            else setCurrentChunkIndex(idx);
          }}
          speed={settings.speed}
          onChangeSpeed={(s) => handleUpdateSettings({ speed: s })}
          volume={settings.volume}
          onChangeVolume={(v) => handleUpdateSettings({ volume: v })}
          autoNext={settings.auto_next}
          onToggleAutoNext={() => handleUpdateSettings({ auto_next: !settings.auto_next })}
          onOpenExportModal={() => setIsExportOpen(true)}
          currentVoiceName={currentVoiceName}
        />
      )}

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onUpdateSettings={(newSet) => {
          if (newSet.edge_voice && newSet.edge_voice !== settings.edge_voice) {
            handleVoiceChange(newSet.edge_voice);
          } else {
            handleUpdateSettings(newSet);
          }
        }}
        voices={voices}
        theme={theme}
        onChangeTheme={setTheme}
        fontSize={fontSize}
        onChangeFontSize={setFontSize}
        fontFamily={fontFamily}
        onChangeFontFamily={setFontFamily}
      />

      {/* Import / Add Story Modal */}
      <ImportModal
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onAddChapters={handleAddChapters}
      />

      {/* Export to MP3 Modal (Single & Grouped Chapters) */}
      <ExportModal
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        chapters={chapters}
        currentChapterId={currentChapterId}
        voice={settings.edge_voice}
        speed={settings.speed}
        chunkSize={settings.chunk_size}
      />
    </div>
  );
};
