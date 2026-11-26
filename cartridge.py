

MIRROR_HORIZONTAL = 0
MIRROR_VERTICAL   = 1
MIRROR_SINGLE_LO  = 2
MIRROR_SINGLE_HI  = 3
MIRROR_FOUR       = 4


class Cartridge:
    def __init__(self, path):
        with open(path, 'rb') as f:
            data = f.read()

        if data[:4] != b'NES\x1a':
            raise ValueError("Not a valid iNES ROM")

        prg_banks = data[4]
        chr_banks = data[5]
        flags6    = data[6]
        flags7    = data[7]

        mapper_lo = (flags6 >> 4) & 0xF
        mapper_hi = (flags7 >> 4) & 0xF
        self.mapper_id = (mapper_hi << 4) | mapper_lo

        has_trainer = bool(flags6 & 0x04)
        offset = 16 + (512 if has_trainer else 0)

        prg_size = prg_banks * 16384
        chr_size = chr_banks * 8192

        self.prg_rom = bytearray(data[offset: offset + prg_size])
        offset += prg_size

        if chr_size > 0:
            self.chr_rom = bytearray(data[offset: offset + chr_size])
            self.chr_is_ram = False
        else:
            self.chr_rom = bytearray(8192)  
            self.chr_is_ram = True

        if flags6 & 0x08:
            self.mirror = MIRROR_FOUR
        elif flags6 & 0x01:
            self.mirror = MIRROR_VERTICAL
        else:
            self.mirror = MIRROR_HORIZONTAL

        self._prg_banks = prg_banks

        
        if self.mapper_id == 1:
            self._mmc1_shift = 0x10
            self._mmc1_ctrl  = 0x0C
            self._mmc1_chr0  = 0
            self._mmc1_chr1  = 0
            self._mmc1_prg   = 0
        elif self.mapper_id == 2:
            self._uxrom_bank = 0
        elif self.mapper_id == 3:
            self._cnrom_bank = 0
        elif self.mapper_id == 4:
            self._mmc3_regs     = [0] * 8
            self._mmc3_target   = 0
            self._mmc3_prg_mode = 0
            self._mmc3_chr_mode = 0
            self._mmc3_irq_latch   = 0
            self._mmc3_irq_counter = 0
            self._mmc3_irq_enable  = False
            self.irq_pending = False

    

    def cpu_read(self, addr):
        if self.mapper_id == 0:
            return self._nrom_prg_read(addr)
        elif self.mapper_id == 1:
            return self._mmc1_prg_read(addr)
        elif self.mapper_id == 2:
            return self._uxrom_prg_read(addr)
        elif self.mapper_id == 3:
            return self._nrom_prg_read(addr)  
        elif self.mapper_id == 4:
            return self._mmc3_prg_read(addr)
        return 0

    def cpu_write(self, addr, data):
        if self.mapper_id == 1:
            self._mmc1_write(addr, data)
        elif self.mapper_id == 2:
            self._uxrom_bank = data & (len(self.prg_rom) // 16384 - 1)
        elif self.mapper_id == 3:
            self._cnrom_bank = data & (len(self.chr_rom) // 8192 - 1)
        elif self.mapper_id == 4:
            self._mmc3_write(addr, data)

    

    def ppu_read(self, addr):
        addr &= 0x1FFF
        if self.mapper_id == 1:
            return self._mmc1_chr_read(addr)
        elif self.mapper_id == 3:
            return self.chr_rom[self._cnrom_bank * 8192 + addr]
        elif self.mapper_id == 4:
            return self._mmc3_chr_read(addr)
        return self.chr_rom[addr]

    def ppu_write(self, addr, data):
        if self.chr_is_ram:
            addr &= 0x1FFF
            self.chr_rom[addr] = data

    

    def _nrom_prg_read(self, addr):
        if self._prg_banks == 1:
            return self.prg_rom[addr & 0x3FFF]
        return self.prg_rom[addr & 0x7FFF]

    

    def _mmc1_prg_read(self, addr):
        ctrl_prg = (self._mmc1_ctrl >> 2) & 3
        bank = self._mmc1_prg & 0x0F
        n = len(self.prg_rom) // 16384
        if ctrl_prg in (0, 1):
            idx = ((bank & ~1) * 16384 + (addr & 0x7FFF)) % len(self.prg_rom)
        elif ctrl_prg == 2:
            if addr < 0xC000:
                idx = addr & 0x3FFF
            else:
                idx = (bank * 16384 + (addr & 0x3FFF)) % len(self.prg_rom)
        else:
            if addr < 0xC000:
                idx = (bank * 16384 + (addr & 0x3FFF)) % len(self.prg_rom)
            else:
                idx = ((n - 1) * 16384 + (addr & 0x3FFF)) % len(self.prg_rom)
        return self.prg_rom[idx]

    def _mmc1_chr_read(self, addr):
        if (self._mmc1_ctrl >> 4) & 1:
            if addr < 0x1000:
                idx = self._mmc1_chr0 * 4096 + (addr & 0x0FFF)
            else:
                idx = self._mmc1_chr1 * 4096 + (addr & 0x0FFF)
        else:
            idx = (self._mmc1_chr0 & ~1) * 4096 + addr
        return self.chr_rom[idx % len(self.chr_rom)]

    def _mmc1_write(self, addr, data):
        if data & 0x80:
            self._mmc1_shift = 0x10
            self._mmc1_ctrl |= 0x0C
            return
        self._mmc1_shift = ((self._mmc1_shift >> 1) | ((data & 1) << 4))
        if self._mmc1_shift & 0x01 == 0:
            return
        val = (self._mmc1_shift >> 1) & 0x1F
        self._mmc1_shift = 0x10
        reg = (addr >> 13) & 3
        if reg == 0:
            self._mmc1_ctrl = val
            m = val & 3
            if m == 0:   self.mirror = MIRROR_SINGLE_LO
            elif m == 1: self.mirror = MIRROR_SINGLE_HI
            elif m == 2: self.mirror = MIRROR_VERTICAL
            else:        self.mirror = MIRROR_HORIZONTAL
        elif reg == 1:
            self._mmc1_chr0 = val
        elif reg == 2:
            self._mmc1_chr1 = val
        else:
            self._mmc1_prg = val

    

    def _uxrom_prg_read(self, addr):
        n = len(self.prg_rom) // 16384
        if addr < 0xC000:
            idx = (self._uxrom_bank * 16384 + (addr & 0x3FFF)) % len(self.prg_rom)
        else:
            idx = ((n - 1) * 16384 + (addr & 0x3FFF)) % len(self.prg_rom)
        return self.prg_rom[idx]

    

    def _mmc3_prg_read(self, addr):
        n = len(self.prg_rom) // 8192
        if self._mmc3_prg_mode == 0:
            banks = [self._mmc3_regs[6], self._mmc3_regs[7], n - 2, n - 1]
        else:
            banks = [n - 2, self._mmc3_regs[7], self._mmc3_regs[6], n - 1]
        slot = (addr - 0x8000) // 0x2000
        idx = (banks[slot] % n) * 8192 + (addr & 0x1FFF)
        return self.prg_rom[idx % len(self.prg_rom)]

    def _mmc3_chr_read(self, addr):
        n_chr = len(self.chr_rom) // 1024
        if self._mmc3_chr_mode == 0:
            banks = [
                self._mmc3_regs[0] & ~1, (self._mmc3_regs[0] & ~1) + 1,
                self._mmc3_regs[1] & ~1, (self._mmc3_regs[1] & ~1) + 1,
                self._mmc3_regs[2], self._mmc3_regs[3],
                self._mmc3_regs[4], self._mmc3_regs[5],
            ]
        else:
            banks = [
                self._mmc3_regs[2], self._mmc3_regs[3],
                self._mmc3_regs[4], self._mmc3_regs[5],
                self._mmc3_regs[0] & ~1, (self._mmc3_regs[0] & ~1) + 1,
                self._mmc3_regs[1] & ~1, (self._mmc3_regs[1] & ~1) + 1,
            ]
        slot = addr // 1024
        idx = (banks[slot] % n_chr) * 1024 + (addr & 0x3FF)
        return self.chr_rom[idx % len(self.chr_rom)]

    def _mmc3_write(self, addr, data):
        if addr < 0xA000:
            if addr & 1:
                self._mmc3_regs[self._mmc3_target] = data
            else:
                self._mmc3_target   = data & 7
                self._mmc3_prg_mode = (data >> 6) & 1
                self._mmc3_chr_mode = (data >> 7) & 1
        elif addr < 0xC000:
            if addr & 1:
                pass  
            else:
                m = data & 1
                self.mirror = MIRROR_VERTICAL if m == 0 else MIRROR_HORIZONTAL
        elif addr < 0xE000:
            if addr & 1:
                self._mmc3_irq_counter = 0
            else:
                self._mmc3_irq_latch = data
        else:
            if addr & 1:
                self._mmc3_irq_enable = True
            else:
                self._mmc3_irq_enable = False
                self.irq_pending = False

    def mmc3_scanline(self):
        if self._mmc3_irq_counter == 0:
            self._mmc3_irq_counter = self._mmc3_irq_latch
        else:
            self._mmc3_irq_counter -= 1
        if self._mmc3_irq_counter == 0 and self._mmc3_irq_enable:
            self.irq_pending = True
