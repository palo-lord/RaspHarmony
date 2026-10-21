from micropython import const
import framebuf

# comandos SH1107
_SET_CONTRAST = const(0x81)
_SET_NORM_INV = const(0xA6)
_SET_DISP = const(0xAE)
_SET_SCAN_DIR = const(0xC0)
_SET_SEG_REMAP = const(0xA0)
_SET_LOW_COLUMN = const(0x00)
_SET_HIGH_COLUMN = const(0x10)
_SET_PAGE_ADDRESS = const(0xB0)

class SH1107(framebuf.FrameBuffer):
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def init_display(self):
        for cmd in (
            _SET_DISP,
            0xDC,
            0x00,
            0x81,
            0x6F,
            0x20,
            0xA0,
            0xC0,
            0xA6,
            0xA8,
            self.height - 1,
            0xD3,
            0x00,
            0xD5,
            0x80,
            0xD9,
            0x22,
            0xDB,
            0x35,
            0xAD,
            0x8A,
            0xAF,
        ):
            self.write_cmd(cmd)

        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(_SET_DISP)

    def poweron(self):
        self.write_cmd(_SET_DISP | 0x01)

    def contrast(self, contrast):
        self.write_cmd(_SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(_SET_NORM_INV | (invert & 1))

    def show(self):
        for page in range(self.pages):
            self.write_cmd(_SET_PAGE_ADDRESS + page)
            self.write_cmd(_SET_LOW_COLUMN + 0)
            self.write_cmd(_SET_HIGH_COLUMN + 0)

            start = page * self.width
            end = start + self.width
            self.write_data(self.buffer[start:end])

class SH1107_I2C(SH1107):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.write_list = [b'\x40', None]
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        self.write_list[1] = buf
        self.i2c.writevto(self.addr, self.write_list)