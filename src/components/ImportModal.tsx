import React, { useState } from 'react';
import { X, Upload, FileText, CheckCircle2, AlertCircle, ArrowDownAZ, ArrowUpZA, Trash2 } from 'lucide-react';
import { Chapter } from '../types';

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddChapters: (newChapters: Chapter[]) => void;
}

export function naturalSortFiles(files: { name: string; content: string }[], ascending = true) {
  return [...files].sort((a, b) => {
    const res = a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    return ascending ? res : -res;
  });
}

export const ImportModal: React.FC<ImportModalProps> = ({
  isOpen,
  onClose,
  onAddChapters,
}) => {
  const [activeTab, setActiveTab] = useState<'upload' | 'paste'>('upload');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [author, setAuthor] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; content: string }[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isAscending, setIsAscending] = useState(true);

  if (!isOpen) return null;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsLoadingFiles(true);
    const filesArray = Array.from(files);

    Promise.all(
      filesArray.map((file) => {
        return new Promise<{ name: string; content: string }>((resolve) => {
          const reader = new FileReader();
          reader.onload = (event) => {
            const text = (event.target?.result as string) || '';
            resolve({
              name: file.name.replace(/\.[^/.]+$/, ''),
              content: text,
            });
          };
          reader.onerror = () => {
            resolve({
              name: file.name.replace(/\.[^/.]+$/, ''),
              content: '',
            });
          };
          reader.readAsText(file, 'utf-8');
        });
      })
    ).then((results) => {
      const validResults = results.filter((r) => r.content.trim().length > 0);
      setUploadedFiles((prev) => {
        const combined = [...prev, ...validResults];
        return naturalSortFiles(combined, isAscending);
      });
      setIsLoadingFiles(false);
    });
  };

  const handleToggleSort = () => {
    const newAsc = !isAscending;
    setIsAscending(newAsc);
    setUploadedFiles((prev) => naturalSortFiles(prev, newAsc));
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleClearAllFiles = () => {
    setUploadedFiles([]);
  };

  const handleSavePaste = () => {
    if (!content.trim()) return;
    const newChap: Chapter = {
      id: `custom-${Date.now()}`,
      title: title.trim() || `Truyện mới ${new Date().toLocaleDateString('vi-VN')}`,
      author: author.trim() || 'Người dùng',
      content: content.trim(),
    };
    onAddChapters([newChap]);
    onClose();
  };

  const handleSaveUploaded = () => {
    if (uploadedFiles.length === 0) return;
    const newChaps: Chapter[] = uploadedFiles.map((f, idx) => ({
      id: `file-${Date.now()}-${idx}`,
      title: f.name,
      author: 'File tải lên',
      content: f.content,
    }));
    onAddChapters(newChaps);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl max-w-xl w-full p-6 text-neutral-100 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-neutral-800 mb-5">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Upload className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Thêm truyện đọc mới</h2>
              <p className="text-xs text-neutral-400">
                Tự động sắp xếp tuần tự theo số chương (chap1 → chap100)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-neutral-400 hover:text-white rounded-lg hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab switch */}
        <div className="flex border-b border-neutral-800 mb-5 text-xs font-semibold">
          <button
            onClick={() => setActiveTab('upload')}
            className={`pb-2.5 px-4 transition-colors relative ${
              activeTab === 'upload'
                ? 'text-indigo-400 border-b-2 border-indigo-500'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            Tải lên nhiều file .TXT (Tự xếp tuần tự)
          </button>
          <button
            onClick={() => setActiveTab('paste')}
            className={`pb-2.5 px-4 transition-colors relative ${
              activeTab === 'paste'
                ? 'text-indigo-400 border-b-2 border-indigo-500'
                : 'text-neutral-400 hover:text-neutral-200'
            }`}
          >
            Dán nội dung văn bản
          </button>
        </div>

        {activeTab === 'upload' ? (
          <div className="space-y-4">
            <div className="border-2 border-dashed border-neutral-700 hover:border-indigo-500/60 rounded-2xl p-6 text-center transition-colors">
              <input
                type="file"
                accept=".txt"
                multiple
                id="file-upload"
                onChange={handleFileUpload}
                className="hidden"
              />
              <label
                htmlFor="file-upload"
                className="cursor-pointer flex flex-col items-center justify-center gap-2"
              >
                <div className="w-12 h-12 rounded-full bg-neutral-800 flex items-center justify-center text-indigo-400">
                  <FileText className="w-6 h-6" />
                </div>
                <span className="text-sm font-semibold text-neutral-200">
                  Chọn một hoặc nhiều file .txt (VD: chap1.txt ... chap100.txt)
                </span>
                <span className="text-xs text-neutral-500">
                  Hệ thống tự động nhận diện và sắp xếp đúng thứ tự từ chap 1 đến chap 100
                </span>
              </label>
            </div>

            {isLoadingFiles && (
              <p className="text-xs text-indigo-400 animate-pulse text-center">
                Đang đọc và sắp xếp các file truyện...
              </p>
            )}

            {uploadedFiles.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-neutral-300">
                    Đã tải {uploadedFiles.length} file (Sắp xếp tuần tự):
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleToggleSort}
                      className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                      title="Đổi chiều sắp xếp"
                    >
                      {isAscending ? (
                        <>
                          <ArrowDownAZ className="w-3.5 h-3.5" />
                          <span>1 → {uploadedFiles.length}</span>
                        </>
                      ) : (
                        <>
                          <ArrowUpZA className="w-3.5 h-3.5" />
                          <span>{uploadedFiles.length} → 1</span>
                        </>
                      )}
                    </button>
                    <span>|</span>
                    <button
                      onClick={handleClearAllFiles}
                      className="text-neutral-400 hover:text-rose-400 transition-colors"
                    >
                      Xóa hết
                    </button>
                  </div>
                </div>

                <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                  {uploadedFiles.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-2 rounded-lg bg-neutral-800 text-xs border border-neutral-700/60"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="w-6 h-5 rounded bg-indigo-500/20 text-indigo-300 font-mono text-[11px] flex items-center justify-center shrink-0">
                          #{i + 1}
                        </span>
                        <span className="truncate max-w-[260px] font-medium text-neutral-200">
                          {f.name}.txt
                        </span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-neutral-400 font-mono text-[11px]">
                          {f.content.trim().split(/\s+/).length.toLocaleString()} từ
                        </span>
                        <button
                          onClick={() => handleRemoveFile(i)}
                          className="text-neutral-500 hover:text-rose-400 transition-colors"
                          title="Xóa file này"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="pt-4 border-t border-neutral-800 flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-neutral-400 hover:text-white"
              >
                Hủy
              </button>
              <button
                onClick={handleSaveUploaded}
                disabled={uploadedFiles.length === 0}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white px-5 py-2 rounded-xl font-medium text-xs shadow-md shadow-indigo-600/30 transition-colors"
              >
                Thêm {uploadedFiles.length} chương vào danh sách
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3.5 text-xs">
            <div>
              <label className="block text-neutral-400 mb-1">Tiêu đề chương / truyện</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Nhập tên truyện..."
                className="w-full bg-neutral-800 border border-neutral-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-neutral-400 mb-1">Tác giả (tùy chọn)</label>
              <input
                type="text"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="Tên tác giả..."
                className="w-full bg-neutral-800 border border-neutral-700 rounded-xl px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-neutral-400 mb-1">Nội dung văn bản</label>
              <textarea
                rows={6}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Dán nội dung truyện vào đây..."
                className="w-full bg-neutral-800 border border-neutral-700 rounded-xl p-3 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 leading-relaxed font-sans"
              />
            </div>

            <div className="pt-4 border-t border-neutral-800 flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-neutral-400 hover:text-white"
              >
                Hủy
              </button>
              <button
                onClick={handleSavePaste}
                disabled={!content.trim()}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white px-5 py-2 rounded-xl font-medium text-xs shadow-md shadow-indigo-600/30 transition-colors"
              >
                Lưu và đọc ngay
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
