# NES APU - basic implementation with all 5 channels

import numpy as np

SAMPLE_RATE = 44100
FRAME_RATE  = 60.0988

LENGTH_TABLE = [
    10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
    12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30,
]

DUTY_TABLE = [
    [0, 1, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 0, 0, 0],
    [1, 0, 0, 1, 1, 1, 1, 1],
]

TRIANGLE_TABLE = [
    15,14,13,12,11,10,9,8,7,6,5,4,3,2,1,0,
     0, 1, 2, 3, 4, 5,6,7,8,9,10,11,12,13,14,15,
]

NOISE_TABLE = [
    4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068,
]

DMC_TABLE = [
    428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 84, 72, 54,
]


class Envelope:
    def __init__(self):
        self.start   = False
        self.loop    = False
        self.constant = False
        self.period  = 0
        self.decay   = 0
        self.divider = 0
        self.output  = 0

    def clock(self):
        if self.start:
            self.start   = False
            self.decay   = 15
            self.divider = self.period
        else:
            if self.divider == 0:
                self.divider = self.period
                if self.decay > 0:
                    self.decay -= 1
                elif self.loop:
                    self.decay = 15
            else:
                self.divider -= 1
        self.output = self.period if self.constant else self.decay


class Sweep:
    def __init__(self, channel):
        self.enabled = False
        self.negate  = False
        self.reload  = False
        self.period  = 0
        self.shift   = 0
        self.divider = 0
        self.channel = channel  # 1 or 2 (for ones-complement vs twos-complement)
        self.target  = 0

    def compute_target(self, timer):
        delta = timer >> self.shift
        if self.negate:
            delta = -delta - (1 if self.channel == 1 else 0)
        self.target = timer + delta

    def mute(self, timer):
        return timer < 8 or self.target > 0x7FF

    def clock(self, timer):
        self.compute_target(timer)
        new_timer = timer
        if self.divider == 0 and self.enabled and self.shift > 0 and not self.mute(timer):
            new_timer = self.target
        if self.divider == 0 or self.reload:
            self.divider = self.period
            self.reload  = False
        else:
            self.divider -= 1
        return new_timer


class Pulse:
    def __init__(self, channel):
        self.enabled  = False
        self.duty     = 0
        self.duty_pos = 0
        self.timer    = 0
        self.timer_period = 0
        self.length   = 0
        self.length_halt = False
        self.envelope = Envelope()
        self.sweep    = Sweep(channel)

    def write_ctrl(self, data):
        self.duty = (data >> 6) & 3
        self.length_halt = bool(data & 0x20)
        self.envelope.loop     = self.length_halt
        self.envelope.constant = bool(data & 0x10)
        self.envelope.period   = data & 0x0F

    def write_sweep(self, data):
        self.sweep.enabled = bool(data & 0x80)
        self.sweep.period  = (data >> 4) & 7
        self.sweep.negate  = bool(data & 0x08)
        self.sweep.shift   = data & 7
        self.sweep.reload  = True

    def write_lo(self, data):
        self.timer_period = (self.timer_period & 0x700) | data

    def write_hi(self, data):
        self.timer_period = (self.timer_period & 0x0FF) | ((data & 7) << 8)
        if self.enabled:
            self.length = LENGTH_TABLE[data >> 3]
        self.duty_pos = 0
        self.envelope.start = True

    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            self.duty_pos = (self.duty_pos - 1) & 7
        else:
            self.timer -= 1

    def clock_length(self):
        if not self.length_halt and self.length > 0:
            self.length -= 1

    def clock_sweep(self):
        self.timer_period = self.sweep.clock(self.timer_period)

    def output(self):
        if (not self.enabled or self.length == 0 or
                DUTY_TABLE[self.duty][self.duty_pos] == 0 or
                self.sweep.mute(self.timer_period)):
            return 0
        return self.envelope.output


class Triangle:
    def __init__(self):
        self.enabled       = False
        self.timer         = 0
        self.timer_period  = 0
        self.length        = 0
        self.length_halt   = False
        self.linear_counter= 0
        self.linear_period = 0
        self.linear_reload = False
        self.seq_pos       = 0

    def write_ctrl(self, data):
        self.length_halt   = bool(data & 0x80)
        self.linear_period = data & 0x7F

    def write_lo(self, data):
        self.timer_period = (self.timer_period & 0x700) | data

    def write_hi(self, data):
        self.timer_period = (self.timer_period & 0x0FF) | ((data & 7) << 8)
        if self.enabled:
            self.length = LENGTH_TABLE[data >> 3]
        self.linear_reload = True

    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            if self.length > 0 and self.linear_counter > 0:
                self.seq_pos = (self.seq_pos + 1) & 31
        else:
            self.timer -= 1

    def clock_length(self):
        if not self.length_halt and self.length > 0:
            self.length -= 1

    def clock_linear(self):
        if self.linear_reload:
            self.linear_counter = self.linear_period
        elif self.linear_counter > 0:
            self.linear_counter -= 1
        if not self.length_halt:
            self.linear_reload = False

    def output(self):
        if not self.enabled or self.length == 0 or self.linear_counter == 0:
            return 0
        return TRIANGLE_TABLE[self.seq_pos]


class Noise:
    def __init__(self):
        self.enabled     = False
        self.mode        = False
        self.timer       = 0
        self.timer_period= 0
        self.length      = 0
        self.length_halt = False
        self.envelope    = Envelope()
        self.shift_reg   = 1

    def write_ctrl(self, data):
        self.length_halt = bool(data & 0x20)
        self.envelope.loop     = self.length_halt
        self.envelope.constant = bool(data & 0x10)
        self.envelope.period   = data & 0x0F

    def write_period(self, data):
        self.mode = bool(data & 0x80)
        self.timer_period = NOISE_TABLE[data & 0x0F]

    def write_length(self, data):
        if self.enabled:
            self.length = LENGTH_TABLE[data >> 3]
        self.envelope.start = True

    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            bit = (self.shift_reg >> (6 if self.mode else 1)) & 1
            feedback = (self.shift_reg & 1) ^ bit
            self.shift_reg = (self.shift_reg >> 1) | (feedback << 14)
        else:
            self.timer -= 1

    def clock_length(self):
        if not self.length_halt and self.length > 0:
            self.length -= 1

    def output(self):
        if not self.enabled or self.length == 0 or (self.shift_reg & 1):
            return 0
        return self.envelope.output


class DMC:
    def __init__(self, bus_read):
        self.bus_read    = bus_read
        self.enabled     = False
        self.irq_enable  = False
        self.loop        = False
        self.timer       = 0
        self.timer_period= DMC_TABLE[0]
        self.sample_addr = 0xC000
        self.sample_len  = 0
        self.cur_addr    = 0xC000
        self.remaining   = 0
        self.shift_reg   = 0
        self.bits_remaining = 8
        self.level       = 0
        self.silence     = True
        self.irq_flag    = False

    def write(self, reg, data):
        if reg == 0:
            self.irq_enable   = bool(data & 0x80)
            self.loop         = bool(data & 0x40)
            self.timer_period = DMC_TABLE[data & 0x0F]
        elif reg == 1:
            self.level = data & 0x7F
        elif reg == 2:
            self.sample_addr = 0xC000 + (data << 6)
        elif reg == 3:
            self.sample_len = (data << 4) + 1

    def restart(self):
        self.cur_addr  = self.sample_addr
        self.remaining = self.sample_len

    def clock_timer(self):
        if self.timer == 0:
            self.timer = self.timer_period
            if not self.silence:
                if self.shift_reg & 1:
                    if self.level <= 125: self.level += 2
                else:
                    if self.level >= 2:   self.level -= 2
                self.shift_reg >>= 1
            self.bits_remaining -= 1
            if self.bits_remaining == 0:
                self.bits_remaining = 8
                if self.remaining > 0:
                    self.shift_reg = self.bus_read(self.cur_addr)
                    self.cur_addr  = 0x8000 | ((self.cur_addr + 1) & 0x7FFF)
                    self.remaining -= 1
                    self.silence   = False
                    if self.remaining == 0:
                        if self.loop:
                            self.restart()
                        elif self.irq_enable:
                            self.irq_flag = True
                else:
                    self.silence = True
        else:
            self.timer -= 1

    def output(self):
        return self.level


class APU:
    def __init__(self, bus_read):
        self.pulse1   = Pulse(1)
        self.pulse2   = Pulse(2)
        self.triangle = Triangle()
        self.noise    = Noise()
        self.dmc      = DMC(bus_read)

        self.frame_counter = 0
        self.frame_mode    = 0   # 0=4-step, 1=5-step
        self.irq_inhibit   = False
        self.frame_irq     = False
        self.cycles        = 0

        self.sample_rate   = SAMPLE_RATE
        self.cpu_freq      = 1789773
        self.sample_period = self.cpu_freq / self.sample_rate
        self.sample_accum  = 0.0
        self.samples       = []

    def write(self, addr, data):
        if addr == 0x4000:   self.pulse1.write_ctrl(data)
        elif addr == 0x4001: self.pulse1.write_sweep(data)
        elif addr == 0x4002: self.pulse1.write_lo(data)
        elif addr == 0x4003: self.pulse1.write_hi(data)
        elif addr == 0x4004: self.pulse2.write_ctrl(data)
        elif addr == 0x4005: self.pulse2.write_sweep(data)
        elif addr == 0x4006: self.pulse2.write_lo(data)
        elif addr == 0x4007: self.pulse2.write_hi(data)
        elif addr == 0x4008: self.triangle.write_ctrl(data)
        elif addr == 0x400A: self.triangle.write_lo(data)
        elif addr == 0x400B: self.triangle.write_hi(data)
        elif addr == 0x400C: self.noise.write_ctrl(data)
        elif addr == 0x400E: self.noise.write_period(data)
        elif addr == 0x400F: self.noise.write_length(data)
        elif 0x4010 <= addr <= 0x4013:
            self.dmc.write(addr - 0x4010, data)
        elif addr == 0x4015:
            self.pulse1.enabled   = bool(data & 0x01)
            self.pulse2.enabled   = bool(data & 0x02)
            self.triangle.enabled = bool(data & 0x04)
            self.noise.enabled    = bool(data & 0x08)
            self.dmc.enabled      = bool(data & 0x10)
            if not self.pulse1.enabled:   self.pulse1.length = 0
            if not self.pulse2.enabled:   self.pulse2.length = 0
            if not self.triangle.enabled: self.triangle.length = 0
            if not self.noise.enabled:    self.noise.length = 0
            if not self.dmc.enabled:      self.dmc.remaining = 0
            elif self.dmc.remaining == 0: self.dmc.restart()
            self.dmc.irq_flag = False
        elif addr == 0x4017:
            self.frame_mode   = (data >> 7) & 1
            self.irq_inhibit  = bool(data & 0x40)
            self.frame_counter = 0
            if self.irq_inhibit:
                self.frame_irq = False
            if self.frame_mode:
                self._clock_quarter()
                self._clock_half()

    def read_status(self):
        val = (int(self.pulse1.length > 0)   |
               int(self.pulse2.length > 0)   << 1 |
               int(self.triangle.length > 0) << 2 |
               int(self.noise.length > 0)    << 3 |
               int(self.dmc.remaining > 0)   << 4 |
               int(self.frame_irq)           << 6 |
               int(self.dmc.irq_flag)        << 7)
        self.frame_irq = False
        return val

    def _clock_quarter(self):
        self.pulse1.envelope.clock()
        self.pulse2.envelope.clock()
        self.triangle.clock_linear()
        self.noise.envelope.clock()

    def _clock_half(self):
        self.pulse1.clock_length()
        self.pulse2.clock_length()
        self.triangle.clock_length()
        self.noise.clock_length()
        self.pulse1.clock_sweep()
        self.pulse2.clock_sweep()

    def clock(self):
        # Clock timers every CPU cycle (triangle) or every other (pulse/noise)
        self.triangle.clock_timer()
        if self.cycles & 1:
            self.pulse1.clock_timer()
            self.pulse2.clock_timer()
            self.noise.clock_timer()
        self.dmc.clock_timer()

        # Frame counter (4-step or 5-step sequencer)
        self.frame_counter += 1
        seq4 = [3729, 7457, 11186, 14915]
        seq5 = [3729, 7457, 11186, 14915, 18641]
        seq  = seq5 if self.frame_mode else seq4
        fc   = self.frame_counter
        if fc == seq[0] or fc == seq[2]:
            self._clock_quarter()
        elif fc == seq[1]:
            self._clock_quarter()
            self._clock_half()
        elif fc == seq[3] if not self.frame_mode else fc == seq[4]:
            self._clock_quarter()
            self._clock_half()
            self.frame_counter = 0
            if not self.frame_mode and not self.irq_inhibit:
                self.frame_irq = True

        # Sample generation
        self.sample_accum += 1.0
        if self.sample_accum >= self.sample_period:
            self.sample_accum -= self.sample_period
            self.samples.append(self._mix())

        self.cycles += 1

    def _mix(self):
        p1 = self.pulse1.output()
        p2 = self.pulse2.output()
        t  = self.triangle.output()
        n  = self.noise.output()
        d  = self.dmc.output()

        pulse_out  = 0.00752 * (p1 + p2)  if (p1 + p2) else 0.0
        tnd_out    = (0.00851 * t + 0.00494 * n + 0.00335 * d) if (t + n + d) else 0.0
        return pulse_out + tnd_out

    def get_samples(self):
        s = self.samples
        self.samples = []
        return s
