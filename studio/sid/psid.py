# SPDX-License-Identifier: GPL-3.0-or-later
# Part of the YAZS Studio project: https://github.com/Ptr314/yazs-studio
"""Заголовок PSID/RSID версий 1-4 (формат HVSC, SID_file_format.txt)"""

import struct


class SidFile(object):
    def __init__(self, path):
        d = open(path, "rb").read()
        self.path = path
        self.magic = d[:4].decode("latin-1")
        if self.magic not in ("PSID", "RSID"):
            raise ValueError("не PSID/RSID: %r" % d[:4])
        (self.version, self.data_offset, self.load, self.init, self.play, self.songs,
         self.start_song, self.speed) = struct.unpack(">HHHHHHHI", d[4:22])

        def txt(b):
            return b.split(b"\0")[0].decode("latin-1")
        self.name, self.author, self.released = txt(d[22:54]), txt(d[54:86]), txt(d[86:118])
        self.flags = self.start_page = self.page_len = self.sid2 = self.sid3 = 0
        if self.version >= 2 and self.data_offset >= 0x7C:
            self.flags, self.start_page, self.page_len, self.sid2, self.sid3 = struct.unpack(
                ">HBBBB", d[118:124])
        body = d[self.data_offset:]
        if self.load == 0:
            self.load = body[0] | (body[1] << 8)
            body = body[2:]
        self.data = body
        if self.init == 0:
            self.init = self.load
        self.end = self.load + len(body) - 1

    @property
    def mus(self):
        return bool(self.flags & 1)

    @property
    def clock(self):
        return ["не указана", "PAL", "NTSC", "PAL/NTSC"][(self.flags >> 2) & 3]

    @property
    def model(self):
        return ["не указана", "6581", "8580", "6581/8580"][(self.flags >> 4) & 3]

    def cia_speed(self, song):
        """True - play вызывается таймером CIA (у PSID по умолчанию 60 Гц), False - кадром"""
        return bool(self.speed >> min(song - 1, 31) & 1) or self.magic == "RSID"

    def describe(self):
        s = "%s v%d «%s» / %s / %s\n" % (self.magic, self.version, self.name, self.author, self.released)
        s += "  данные $%04X-$%04X (%d байт), init $%04X, play $%04X, мелодий %d (начальная %d)\n" % (
            self.load, self.end, len(self.data), self.init, self.play, self.songs, self.start_song)
        s += "  частота %s, SID %s, speed $%08X%s%s" % (
            self.clock, self.model, self.speed, ", MUS" if self.mus else "",
            (", второй SID $D%03X" % (self.sid2 << 4)) if self.sid2 else "")
        return s
