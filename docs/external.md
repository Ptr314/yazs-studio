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

Чего здесь нет, но может понадобиться (ссылки - в `docs/card.md` и `docs/roadmap.md`):
- записи демо НКЛ с живой платы (agatcomp.ru/agat/Hardware/SoundNCL/SoftNCL/DemoNCL/);
- архив мелодий `.MUS` (`forum.agatcomp.ru/static_images/music.rar`, 31 МБ);
- MuzCell, плеер Tigoro с дизассемблером PLAYERR.

Скачивание - только с согласия владельца проекта, по одному файлу, с указанием имени, источника и
размера.
