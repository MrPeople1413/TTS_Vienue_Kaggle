# 📖 Đọc Truyện TTS Tiếng Việt

Ứng dụng đọc truyện tiếng Việt với giọng nữ tự nhiên, hỗ trợ file dài 10.000–100.000+ từ.

---

## 🚀 Cài đặt nhanh

### Bước 1: Cài Python 3.10+
Tải tại https://www.python.org/downloads/ — nhớ tick **"Add Python to PATH"**

### Bước 2: Chạy file cài đặt
```
Double-click vào: install.bat
```

### Bước 3: Chạy ứng dụng
```
Double-click vào: run.bat
hoặc: python main.py
```

---

## 🎤 So sánh TTS Engine

| Engine | Chất lượng | Internet | Giọng VN | Ghi chú |
|--------|-----------|----------|----------|---------|
| **Edge TTS** ⭐ | ★★★★★ | Cần | HoaiMy Neural | Khuyến nghị |
| gTTS | ★★★☆☆ | Cần | Có | Backup |
| pyttsx3 | ★★☆☆☆ | Không | SAPI5 | Offline |

**Edge TTS được khuyến nghị** vì:
- Giọng `vi-VN-HoaiMyNeural` rất tự nhiên, như audiobook thật
- Miễn phí, không cần API key
- Dùng Microsoft Azure Edge API

---

## ✨ Tính năng

### Nguồn truyện
- Mở file `.txt` đơn lẻ
- Mở cả folder, hiển thị danh sách
- Đọc liên tục, tự động chuyển file tiếp theo

### Điều khiển
- Play / Pause / Stop
- Next / Previous file
- Skip forward 5 đoạn
- Thanh tiến trình đọc

### Lưu vị trí
- Tự động lưu vị trí đọc mỗi đoạn
- Khi mở lại: tiếp tục từ chỗ dừng

### Tùy chỉnh
- Tốc độ đọc: 0.5x – 2.0x
- Âm lượng: 0% – 100%
- Chọn giọng đọc
- Tự động chuyển file tiếp theo

### Xuất Audio
- Xuất toàn bộ truyện ra file MP3
- Hỗ trợ WAV

---

## 🔧 Xử lý file rất dài

Ứng dụng chia văn bản thành **chunks nhỏ 200 ký tự**, đọc từng chunk:
- Không load toàn bộ file vào RAM
- Không bị treo UI (dùng threading)
- Tự động retry 3 lần nếu lỗi mạng
- Bỏ qua chunk lỗi, tiếp tục đọc

---

## 📁 Cấu trúc file

```
viet_tts_reader/
├── main.py          # Code chính
├── requirements.txt # Thư viện cần cài
├── install.bat      # Script cài đặt Windows
├── run.bat          # Script chạy ứng dụng
└── README.md        # Tài liệu này
```

Cài đặt lưu tại: `C:\Users\<tên>\\.viet_tts_reader\`
- `settings.json` — cài đặt ứng dụng
- `positions.json` — vị trí đọc từng file

---

## ❓ Lỗi thường gặp

**"Không tìm thấy TTS engine"**
→ Chạy lại `install.bat`

**Giọng đọc không tự nhiên / quá nhanh**
→ Điều chỉnh thanh "Tốc độ" về 0.9x–1.0x

**Bị lỗi khi đọc file dài**
→ Ứng dụng tự động bỏ qua và đọc tiếp. Kiểm tra kết nối mạng.

**File .txt bị lỗi font / không đọc được**
→ Thử lưu lại file với encoding UTF-8 (dùng Notepad++ → Save As → UTF-8)
