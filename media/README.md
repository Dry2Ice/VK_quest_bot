Кладите сюда картинки/видео квеста под именами из config.py:

  qr2.jpg       — фото/подсказка локации QR2 (QR2_PHOTO_FILE)
  qr3.jpg       — фото/подсказка локации QR3 (QR3_PHOTO_FILE)
  rebus.jpg     — картинка с ребусом (REBUS_PHOTO_FILE)
  congrats.jpg  — фото Бипа с поздравлением (CONGRATS_PHOTO_FILE)
  route.mp4     — видео-маршрут до павильона (ROUTE_VIDEO_FILE)

При старте бот сам загрузит эти файлы в VK и запомнит готовые
attachment-строки в media_cache.json — заново грузиться будет только
изменённый файл. Имена файлов можно поменять через .env (см. .env.example).

Эта папка не обязана лежать в media_cache.json/git — сам media_cache.json
пересоздаётся автоматически.
