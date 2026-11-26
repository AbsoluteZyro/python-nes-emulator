

from ppu import PPU
from apu import APU
from controller import Controller


class Bus:
    def __init__(self, cartridge):
        self.cart        = cartridge
        self.ram         = bytearray(2048)
        self.ppu         = PPU(cartridge)
        self.apu         = APU(self.cpu_read)
        self.controller1 = Controller()
        self.controller2 = Controller()

        from cpu import CPU
        self.cpu = CPU(self)

        self.dma_active   = False
        self.dma_page     = 0x00
        self.dma_cycle    = False
        self._ppu_tick    = 0

    def reset(self):
        self.cpu.reset()
        self.ppu.stat_vblank = 0
        self.ppu.cycles = 0

    

    def cpu_read(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x07FF]
        elif addr < 0x4000:
            return self.ppu.cpu_read(addr)
        elif addr == 0x4015:
            return self.apu.read_status()
        elif addr == 0x4016:
            return self.controller1.read()
        elif addr == 0x4017:
            return self.controller2.read()
        elif addr >= 0x4020:
            return self.cart.cpu_read(addr)
        return 0

    def cpu_write(self, addr, data):
        addr &= 0xFFFF
        data &= 0xFF
        if addr < 0x2000:
            self.ram[addr & 0x07FF] = data
        elif addr < 0x4000:
            self.ppu.cpu_write(addr, data)
        elif addr == 0x4014:
            self.dma_page   = data
            self.dma_active = True
        elif addr == 0x4016:
            self.controller1.write(data)
            self.controller2.write(data)
        elif 0x4000 <= addr <= 0x4017:
            self.apu.write(addr, data)
        elif addr >= 0x4020:
            self.cart.cpu_write(addr, data)

    

    def clock(self):
        self.ppu.clock()
        if self.ppu.nmi_output:
            self.cpu.nmi()

        self._ppu_tick += 1
        if self._ppu_tick % 3 == 0:
            if self.dma_active:
                if not self.dma_cycle:
                    self.dma_cycle = True
                else:
                    self.ppu.dma_write(self.dma_page, self.cpu_read)
                    self.dma_active = False
                    self.dma_cycle  = False
            else:
                self.cpu.clock()
                self.apu.clock()

        
        if hasattr(self.cart, 'irq_pending') and self.cart.irq_pending:
            self.cart.irq_pending = False
            self.cpu.irq()

    @property
    def frame_ready(self):
        return self.ppu.frame_ready

    def consume_frame(self):
        self.ppu.frame_ready = False
        return self.ppu.frame_buffer
