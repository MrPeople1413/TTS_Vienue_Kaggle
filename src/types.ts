export interface Chapter {
  id: string;
  title: string;
  author?: string;
  source?: string;
  content: string;
}

export interface AppSettings {
  engine: 'edge_tts' | 'browser' | 'vieneu';
  edge_voice: string;
  vieneu_voice: string;
  vieneu_device: 'cpu' | 'gpu';
  speed: number;
  volume: number;
  chunk_size: number;
  export_workers: number;
  vieneu_threads: number;
  auto_next: boolean;
  use_cache: boolean;
  kaggle_username: string;
  kaggle_api_key: string;
  kaggle_dataset_slug: string;
  kaggle_kernel_slug: string;
  kaggle_batch_voice: string;
  kaggle_batch_size: number;
  kaggle_poll_sec: number;
}

export interface VoiceOption {
  id: string;
  name: string;
  gender: 'Female' | 'Male' | 'Neutral';
  locale: string;
  engine: 'edge_tts' | 'browser' | 'vieneu';
  recommended?: boolean;
}

export interface ReadingPosition {
  chapterId: string;
  chunkIndex: number;
  updatedAt: number;
}
