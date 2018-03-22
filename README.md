# vrnbus
Прогноз прибытия автобусов в Воронеже. 
Веб-версия: https://vrnbus.herokuapp.com 
Телеграм-бот: https://t.me/vrnbusbot

# Техническое

Front-end: чистый JavaScript и поддержка fetch/promises для старых браузеров

Back-end: Python 3.6 (cachetools, fdb, python-telegram-bot, pytz, tornado)

# Видео о проекте
https://www.youtube.com/watch?v=1OtHwGqSL04

# Установка
* Установить Python 3.6 или новее
* `pip install -r requirements.txt`
* Распаковать `test_data.7z` в каталог `test_data`
* Создать Телеграм-бота для тестов с помощью бота
 [@BotFather](https://t.me/BotFather) и получить его токен
* Указать токен в `settings.py` или в переменной окружения VRNBUSBOT_TOKEN
* Запустить `main.py` и открыть [http://localhost:8080](http://localhost:8080).