@echo off
echo ====================================
echo  Cai dat Edge TTS + Pygame
echo ====================================
echo.

py -3.10 install edge-tts
echo.
py -3.10 install pygame
echo.

python -c "import edge_tts; print('OK: edge-tts')"
python -c "import pygame; print('OK: pygame')"

echo.
echo Xong! Chay run.bat de mo ung dung.
pause
