# Внешние материалы (`docs-external/`, не в git)

Каталог в `.gitignore`: чужие диски, записи, схемы и ноты не распространяются с проектом. Здесь
написано, что в нем лежит у разработчика и откуда это брать.

| Путь | Что | Откуда |
|---|---|---|
| `sound/agat-sound-schem.pdf` | схема ЯЗС 5/2 (перерисованная; известные ошибки - `docs/card.md`) | agatcomp.ru, раздел ЯЗС |
| `sound/YAZS_Test.wav` | запись авторежима SOUNDTEST с настоящей платы (неисправна: D0 ударного 6) | форум agatcomp |
| `sound/soundtest.DSK`, `SOUNDTEST.bin`, `snd_test.bas`, `soundtest.txt`, `readme.txt` | диск SOUNDTEST с «Быстропускалкой» V2.0 - из него сделан `disk/template840.dsk` | форум agatcomp |
| `sound/music-d.DSK` | демо НКЛ (песня), тот же, что `deploy/software/agat/music-d.dsk` в eCat3 | agatcomp.ru |
| `sid-examples/*.sid` | 8 мелодий C64 (PSID v2) для конвертера: Alice in Wonderland, Frostbyte, Joe Blade 2, Legend Intro, Robin of the Wood, RoboCop 3, Saboteur II, Spellbound Dizzy | HVSC |
| `notes-sources/entertainer.ly` | The Entertainer, набор Mutopia-2008/12/21-263 | mutopiaproject.org |
| `notes-sources/sugar-plum-fairy.mid` | Танец Феи Драже, MIDI полной партитуры | открытый MIDI-набор |
| `notes-sources/bumblebee.mid` | Полет шмеля, MIDI | открытый MIDI-набор |
| `notes-sources/anitra-mutopia/` | Танец Анитры, Mutopia № 281: MIDI целиком и по партиям | mutopiaproject.org |
| `notes-sources/IMSLP624090-...pdf` | Песня Сольвейг, ор. 23, C.F. Peters | imslp.org (скачивается вручную: проверка JavaScript) |
| `notes-sources/ritz.pdf` | Puttin' on the Ritz, первое издание 1929 года | скан издания (скачан с разрешения пользователя) |
| `notes-sources/IMSLP57454-PMLP03607-Tchaikovsky_op71_Nutcracker_(pf).pdf` | сюита из «Щелкунчика», ор. 71a, переложение для фортепиано, Jurgenson 1892; Вальс цветов - с. 28-37 | imslp.org (скачан пользователем, ноябрь 2026) |
| `notes-sources/nut7wltz.mid` | Вальс цветов, MIDI фортепианного переложения (R. J. Stratton, Jr.), 389 тактов; местами расходится с изданием Jurgenson (октавные удвоения баса, другая хроматика) | положен пользователем; только для сверки (`gen_flowers.py --compare`) |
| `notes-sources/Waltz-Of-The-Flowers.mid` | сокращенная аранжировка Вальса цветов (68 тактов, фа мажор, GM, без выравнивания) | положен пользователем; не используется |
| `notes-sources/flowers/` | расшифровка сканов клавира (с. 28-37) в тексте, формат - `FORMAT.txt`; источник нот для `gen_flowers.py` | своя (ноты издания в общественном достоянии) |
| `notes-sources/vivaldi/<сезон>/` | «Времена года», ор. 8 № 1-4: `<сезон>-mids.zip` и `<сезон>-lys.zip` с распаковкой (MIDI частей и партии LilyPond), наборы Mutopia № 301, 336, 350, 351 (CC BY-SA 3.0) | mutopiaproject.org/ftp/VivaldiA/O8/ (скачаны с разрешения пользователя, ноябрь 2026) |

Чего здесь нет, но может понадобиться (ссылки - в `docs/card.md` и `docs/roadmap.md`):
- записи демо НКЛ с живой платы (agatcomp.ru/agat/Hardware/SoundNCL/SoftNCL/DemoNCL/);
- архив мелодий `.MUS` (`forum.agatcomp.ru/static_images/music.rar`, 31 МБ);
- MuzCell, плеер Tigoro с дизассемблером PLAYERR.

Скачивание - только с согласия владельца проекта, по одному файлу, с указанием имени, источника и
размера.
