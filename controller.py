# NES controller

# Button bit positions
BTN_A      = 0x80
BTN_B      = 0x40
BTN_SELECT = 0x20
BTN_START  = 0x10
BTN_UP     = 0x08
BTN_DOWN   = 0x04
BTN_LEFT   = 0x02
BTN_RIGHT  = 0x01


class Controller:
    def __init__(self):
        self.state  = 0x00   # current button state
        self.latch  = 0x00   # latched state on strobe
        self.strobe = False

    def write(self, data):
        self.strobe = bool(data & 1)
        if self.strobe:
            self.latch = self.state

    def read(self):
        if self.strobe:
            return (self.state >> 7) & 1
        bit = (self.latch >> 7) & 1
        self.latch = ((self.latch << 1) | 0x01) & 0xFF
        return bit

    def set_button(self, button, pressed):
        if pressed:
            self.state |= button
        else:
            self.state &= ~button
