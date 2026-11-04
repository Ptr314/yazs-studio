# Связь с eCat3

[eCat3](https://github.com/Ptr314/ecat3) - эмулятор, в котором ЯЗС-Студия родилась
(`tools/yazs-player`, 2026-11-03) и который остается ее испытательным стендом. В eCat3 есть:
- модель ячейки 5/2;
- машина Агат-9 с ЯЗС и дисководом 840 КБ;
- консольная сборка, которая пишет звук быстрее реального времени;
- MCP-сервер для живой отладки.

Сама ЯЗС-Студия от кода eCat3 не зависит: сборка диска и модель движка работают без него.
Эмулятор нужен для звука, снимков экрана, сверки плеера с моделью и `.hfe`.

## Где eCat3

| Что | Где ищется | Переменная |
|---|---|---|
| рабочая копия eCat3 | `../eCat3` (рядом с `yazs-studio`) | `ECAT3_DIR` |
| консольный эмулятор для `render.py` | `src/cmake-build-headless`, `cmake-build-mcp`, `cmake-build-headless-mcp` в eCat3 | `ECAT3_HEADLESS` |
| конфигурации машин, ПЗУ | `deploy/` eCat3 | - |

Консольная сборка - по `docs/BUILD.md` eCat3 (`ENABLE_GUI=OFF`, `ENABLE_HEADLESS=ON`). Подойдет и
выпуск `ecat-<версия>-windows-x86_64-HEADLESS.zip`, если положить его `eCat3-headless.exe` в путь из
`ECAT3_HEADLESS`, а `ECAT3_DIR` направить на каталог с `computers/`, `data/`, `software/`:
`render.py` ищет их в `ECAT3_DIR/deploy`.

## Что из eCat3 используется

- **Машина** `deploy/computers/agat/Agat-9-yazs.ext`:
  - Агат-9;
  - ЯЗС в слоте 1 (`$C090`);
  - контроллер 840 КБ в слоте 5 и 140 КБ в слоте 6;
  - моно, 44100 Гц.
- **Модель ячейки** - устройство `agat-yazs` (`src/emulator/devices/specific/agat_yazs.cpp`):
  - аналоговая часть по схеме (RC-огибающие, ключи, полосы, смеситель);
  - номиналы подогнаны по записям двух настоящих плат (`docs/card.md`).

  Если меняется модель, меняется и звук всех мелодий: после правок в eCat3 стоит переслушать
  контрольные части.
- **`render.py`** гоняет `eCat3-headless --no-sound --workdir <свой> --script <сгенерированный.ecat>`:
  - рабочий каталог в `out/.../work` - ссылки на `computers`, `data`, `software` eCat3 и копия
    `.ecat.ini`, так что `deploy/ecat.ini` разработчика не трогается;
  - звук пишется командой `COMMAND sound.record("x.wav")` на `SPEED MAX`;
  - вывод `LOG` - в файл рядом со сценарием.
- **`.hfe`** для Gotek/HxC пишет сам эмулятор: `COMMAND fdd0.save("x.hfe")` (`build.save_hfe`).

## Поля и команды для отладки

Работают и в сценариях `.ecat`, и через MCP (`ecat_run`). Полный словарь - `docs/SCRIPTING.md` eCat3.

| Что | Команда |
|---|---|
| регистры ячейки (последние записи, 16) | `LOG yazs.regs`, `LOG yazs.regs($8,$E)` |
| счета шести ВИ53 (тоны 1-5, таймер) | `LOG yazs.counters` |
| сколько раз взведен флаг таймера | `LOG yazs.irqs` |
| огибающие каналов и ударных, выход смесителя, мВ | `LOG yazs.env`, `LOG yazs.drums`, `LOG yazs.level` |
| ОЗУ (переменные плеера: тики `$1E`, кадр `$14`, канал `$0900+`) | `LOG ram.value($1E,$1F)` |
| карта диспетчера памяти (сегменты 0-15 -> банки) | `LOG port-C1xx.value(0,15)` |
| физическая память банков 8-15 (блоки v2) | `LOG ram.value($10000,$1000F)` |
| процессор | `LOG cpu.registers`, `LOG cpu.disasm($1800,$1840)` |
| останов, шаг, точки останова | `COMMAND cpu.stop()`, `cpu.run()`, `cpu.step()`, `cpu.breakpoint($xxxx)`, `cpu.until($xxxx)`, `cpu.tstep(n)`, `cpu.over()`, `cpu.out()` |
| диск | `COMMAND fdd0.load("C:/путь/x.dsk")`, `fdd0.save("x.hfe")` |
| клавиши | `KEY 100,100,ret` (`down`, `esc`, `right`...) |
| снимок | `SCREEN "x.png"` - лучше при остановленном процессоре |

Адреса меток плеера - в листинге AS65: `out/build/player.lst` после `studio/build.py` (или в каталоге
`--out`).

## MCP: живая отладка из Claude Code

В корне проекта лежит `.mcp.json` - тот же сервер `ecat3`, что в eCat3:
- запускается обертка eCat3 `.build/mcp_reload.py`: она перезапускает эмулятор, когда eCat3
  пересобран;
- сам эмулятор - оконная сборка с MCP `src/cmake-build-mcp/eCat3.exe`;
- рабочий каталог - `deploy/` eCat3.

Пути по умолчанию абсолютные, переопределяются переменными `ECAT3_EXE`, `ECAT3_DEPLOY`,
`ECAT3_RELOADER`, `ECAT3_PYTHON`, `ECAT3_QT_BIN`, `ECAT3_MINGW_BIN` (`docs/MCP.md` eCat3). MCP-сборку
eCat3 собирает сам eCat3: `cmake-build-mcp` - GUI + MCP + OpenGL.

Инструменты сервера:

| Инструмент | Что |
|---|---|
| `ecat_machine` | загрузить машину: `agat/Agat-9-yazs.ext` |
| `ecat_run` | строки `.ecat` по порядку, ответ - их вывод |
| `ecat_screenshot` | снимок экрана картинкой |
| `ecat_describe` | поля и команды устройства (`yazs`, `cpu`, `fdd0`, `main-mapper`...) |
| `ecat_status`, `ecat_devices`, `ecat_cancel` | состояние, список устройств, сброс очереди |

Типичный цикл для новой версии плеера:

1. Собрать диск: `python studio/build.py --disk out/dev.dsk --no-hfe --only test_fx`. Для `.yz`
   подойдет `python studio/listen.py файл.yz`: диск с одной мелодией в `out/listen/`.
2. `ecat_machine` с `agat/Agat-9-yazs.ext`.
3. `ecat_run`:
   ```
   COMMAND fdd0.load("C:/Storages/GoogleDrive/Projects/Emulation/yazs-studio/out/dev.dsk")
   RESET cold
   SPEED MAX
   WAIT 12000
   KEY 100,100,ret
   WAIT 2000
   COMMAND cpu.stop()
   LOG yazs.regs
   LOG ram.value($1E,$1F)
   ```
4. `ecat_screenshot` - меню, пульт или трекер.
5. Точка останова на метке из `player.lst`: `COMMAND cpu.breakpoint($xxxx)`, `COMMAND cpu.run()`,
   затем `LOG cpu.registers`, `LOG ram.value(...)`, `COMMAND cpu.step()`.

`WAIT` считает эмулированное время: если машина не загрузилась или процессор стоит, он ждет вечно
- ставьте `timeout_ms` у `ecat_run`. Строки после `MACHINE` в одном `ecat_run` начинаются с первого
такта машины - так прогон повторяет сценарий один в один.

Для повторяемых проверок лучше сценарии, чем живая сессия: `studio/verify.py`, `studio/listen.py`,
`studio/lostticks.py`, `studio/shots.py`, `studio/brun.py` сами пишут `.ecat` и разбирают вывод
(`docs/development.md`). Пробу с меткой удобно делать так: `PRINT "@имя"`, за ним строки `LOG` - в
выводе они идут подряд (`brun.Scenario`). `COMMAND ram.load("x.bin", $адрес)` записывает байты в
ОЗУ, `COMMAND ram.save("x.bin")` снимает все 128 КБ.
Найденное в живой сессии стоит закрепить таким сценарием.

## Диск и тест в eCat3

В библиотеке eCat3 лежит диск симфонии: `library/agat/yazs-player.dsk` и `.hfe` (описание - `.lst`
рядом, строка в `library/README.md`). Его грузит регрессионный тест
`tests/scripts/work-agat-9-yazs-player.ecat`. Тест проверяет:
- меню из 7 мелодий;
- через 6 с игры первой - число тиков, кадр, регистры и счета ячейки;
- снимки пульта и трекера;
- выход: ячейка остановлена, мотор выключен (так было при выходе в монитор, см. ниже).

Когда меняется плеер или партитуры симфонии:

1. `python studio/build.py --to-ecat3` - собрать и положить `yazs-player.dsk/.hfe` в
   `eCat3/library/agat/`.
2. В eCat3: `py tests/run_tests.py -k yazs-player`. Изменение ожидаемое (например, загрузка стала
   дольше на пару тиков - число тиков через 6 с и снимок пульта) - тогда
   `py tests/run_tests.py --update -k work-agat-9-yazs-player`, затем `git checkout` артефактов,
   которые не должны были меняться: `--update` перезаписывает все.
3. Диск и эталоны коммитятся в eCat3 вместе.

Регрессионного теста для `.YZ` версии 2 в eCat3 пока нет: для него на диск библиотеки нужен файл
v2 (`docs/roadmap.md`). Пока v2 проверяется `studio/checks.py` в этом проекте.

**Диск библиотеки отстает от плеера.** В eCat3 лежит плеер с выходом в монитор. Нынешний выходит к
запустившему (`docs/player.md`, «Запуск»), и при обновлении диска тест надо переписать, а не только
перезаписать эталоны:
- последний шаг теста - «РЕД в меню, РЕД в монитор» и проверка `+F = $C0` и выключенного мотора.
  Теперь после второго РЕД «Быстропускалка» перечитывает каталог (мотор включен) и запускает плеер
  снова, а тот включает таймер ячейки. Проверять стоит, что меню снова на экране;
- меняются и снимки: в меню «РЕД-ВЫХОД», на пульте строки «ВЛЕВО/ВПРАВО-КАДР ВВЕРХ-НАЗАД» и
  «R-ПОВТОР»;
- `$4D` (число файлов), `$1E` и `$14` на месте; число тиков через 6 с может сдвинуться: загрузчик
  копирует тело плеера перед стартом.

## Что остается в eCat3

- Модель ячейки, машина `Agat-9-yazs.ext`, ее описание `Agat-9-yazs.md` (`.en.md`).
- Диск библиотеки и его тест.
- Демо-диск `deploy/software/agat/music-d.dsk` (песня НКЛ).

Правки модели ячейки - дело eCat3: его `CLAUDE.md` и `docs/dev/machines.md`. Если ЯЗС-Студии
понадобится что-то от модели (новое поле для отладки, исправление), это делается в eCat3, а здесь
отмечается в `docs/card.md`.
