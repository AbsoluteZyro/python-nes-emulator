

class CPU:
    def __init__(self, bus):
        self.bus = bus
        self.a = 0x00
        self.x = 0x00
        self.y = 0x00
        self.sp = 0xFD
        self.pc = 0x0000
        
        self.c = 0  
        self.z = 0  
        self.i = 1  
        self.d = 0  
        self.b = 0  
        self.u = 1  
        self.v = 0  
        self.n = 0  

        self.cycles = 0
        self.total_cycles = 0
        self._acc_mode = False
        self._build_opcode_table()

    

    @property
    def status(self):
        return (self.n << 7 | self.v << 6 | self.u << 5 | self.b << 4 |
                self.d << 3 | self.i << 2 | self.z << 1 | self.c)

    @status.setter
    def status(self, value):
        self.n = (value >> 7) & 1
        self.v = (value >> 6) & 1
        self.u = 1
        self.b = (value >> 4) & 1
        self.d = (value >> 3) & 1
        self.i = (value >> 2) & 1
        self.z = (value >> 1) & 1
        self.c = value & 1

    def _set_nz(self, value):
        self.z = 1 if (value & 0xFF) == 0 else 0
        self.n = 1 if (value & 0x80) else 0

    

    def read(self, addr):
        return self.bus.cpu_read(addr & 0xFFFF)

    def write(self, addr, data):
        self.bus.cpu_write(addr & 0xFFFF, data & 0xFF)

    

    def push(self, data):
        self.write(0x0100 + self.sp, data & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def pop(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.read(0x0100 + self.sp)

    

    def reset(self):
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.status = 0x24
        lo = self.read(0xFFFC)
        hi = self.read(0xFFFD)
        self.pc = (hi << 8) | lo
        self.cycles = 8

    def irq(self):
        if self.i == 0:
            self.push((self.pc >> 8) & 0xFF)
            self.push(self.pc & 0xFF)
            self.b = 0
            self.u = 1
            self.i = 1
            self.push(self.status)
            lo = self.read(0xFFFE)
            hi = self.read(0xFFFF)
            self.pc = (hi << 8) | lo
            self.cycles = 7

    def nmi(self):
        self.push((self.pc >> 8) & 0xFF)
        self.push(self.pc & 0xFF)
        self.b = 0
        self.u = 1
        self.i = 1
        self.push(self.status)
        lo = self.read(0xFFFA)
        hi = self.read(0xFFFB)
        self.pc = (hi << 8) | lo
        self.cycles = 8

    def clock(self):
        if self.cycles == 0:
            opcode = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if opcode in self.opcodes:
                op, addr_mode, base_cycles = self.opcodes[opcode]
                self.cycles = base_cycles
                addr, page_crossed = addr_mode()
                extra = op(addr, page_crossed)
                if extra:
                    self.cycles += extra
            
        self.cycles -= 1
        self.total_cycles += 1

    

    def IMP(self):
        self._acc_mode = False
        return 0, False

    def ACC(self):
        self._acc_mode = True
        return 0, False

    def IMM(self):
        self._acc_mode = False
        addr = self.pc
        self.pc = (self.pc + 1) & 0xFFFF
        return addr, False

    def ZPG(self):
        self._acc_mode = False
        addr = self.read(self.pc) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return addr, False

    def ZPX(self):
        self._acc_mode = False
        addr = (self.read(self.pc) + self.x) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return addr, False

    def ZPY(self):
        self._acc_mode = False
        addr = (self.read(self.pc) + self.y) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return addr, False

    def ABS(self):
        self._acc_mode = False
        lo = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        hi = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        return (hi << 8) | lo, False

    def ABX(self):
        self._acc_mode = False
        lo = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        hi = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        base = (hi << 8) | lo
        addr = (base + self.x) & 0xFFFF
        return addr, (addr & 0xFF00) != (base & 0xFF00)

    def ABY(self):
        self._acc_mode = False
        lo = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        hi = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        base = (hi << 8) | lo
        addr = (base + self.y) & 0xFFFF
        return addr, (addr & 0xFF00) != (base & 0xFF00)

    def IND(self):
        self._acc_mode = False
        lo = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        hi = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        ptr = (hi << 8) | lo
        
        if (ptr & 0xFF) == 0xFF:
            addr = (self.read(ptr & 0xFF00) << 8) | self.read(ptr)
        else:
            addr = (self.read(ptr + 1) << 8) | self.read(ptr)
        return addr, False

    def IZX(self):
        self._acc_mode = False
        t = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        ptr = (t + self.x) & 0xFF
        lo = self.read(ptr)
        hi = self.read((ptr + 1) & 0xFF)
        return (hi << 8) | lo, False

    def IZY(self):
        self._acc_mode = False
        ptr = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        lo = self.read(ptr & 0xFF)
        hi = self.read((ptr + 1) & 0xFF)
        base = (hi << 8) | lo
        addr = (base + self.y) & 0xFFFF
        return addr, (addr & 0xFF00) != (base & 0xFF00)

    def REL(self):
        self._acc_mode = False
        offset = self.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        if offset & 0x80:
            offset -= 0x100
        return (self.pc + offset) & 0xFFFF, False

    

    def ADC(self, addr, page):
        data = self.read(addr)
        result = self.a + data + self.c
        self.v = 1 if (~(self.a ^ data) & (self.a ^ result) & 0x80) else 0
        self.c = 1 if result > 0xFF else 0
        self.a = result & 0xFF
        self._set_nz(self.a)
        return 1 if page else 0

    def AND(self, addr, page):
        self.a &= self.read(addr)
        self._set_nz(self.a)
        return 1 if page else 0

    def ASL(self, addr, page):
        if self._acc_mode:
            self.c = (self.a >> 7) & 1
            self.a = (self.a << 1) & 0xFF
            self._set_nz(self.a)
        else:
            data = self.read(addr)
            self.c = (data >> 7) & 1
            result = (data << 1) & 0xFF
            self.write(addr, result)
            self._set_nz(result)
        return 0

    def _branch(self, addr, condition):
        if condition:
            extra = 2 if (addr & 0xFF00) != (self.pc & 0xFF00) else 1
            self.pc = addr
            return extra
        return 0

    def BCC(self, addr, page): return self._branch(addr, self.c == 0)
    def BCS(self, addr, page): return self._branch(addr, self.c == 1)
    def BEQ(self, addr, page): return self._branch(addr, self.z == 1)
    def BMI(self, addr, page): return self._branch(addr, self.n == 1)
    def BNE(self, addr, page): return self._branch(addr, self.z == 0)
    def BPL(self, addr, page): return self._branch(addr, self.n == 0)
    def BVC(self, addr, page): return self._branch(addr, self.v == 0)
    def BVS(self, addr, page): return self._branch(addr, self.v == 1)

    def BIT(self, addr, page):
        data = self.read(addr)
        self.z = 1 if (self.a & data) == 0 else 0
        self.n = (data >> 7) & 1
        self.v = (data >> 6) & 1
        return 0

    def BRK(self, addr, page):
        self.pc = (self.pc + 1) & 0xFFFF
        self.i = 1
        self.push((self.pc >> 8) & 0xFF)
        self.push(self.pc & 0xFF)
        self.b = 1
        self.push(self.status)
        self.b = 0
        lo = self.read(0xFFFE)
        hi = self.read(0xFFFF)
        self.pc = (hi << 8) | lo
        return 0

    def CLC(self, addr, page): self.c = 0; return 0
    def CLD(self, addr, page): self.d = 0; return 0
    def CLI(self, addr, page): self.i = 0; return 0
    def CLV(self, addr, page): self.v = 0; return 0

    def _compare(self, reg, addr, page):
        data = self.read(addr)
        result = (reg - data) & 0xFF
        self.c = 1 if reg >= data else 0
        self._set_nz(result)
        return 1 if page else 0

    def CMP(self, addr, page): return self._compare(self.a, addr, page)
    def CPX(self, addr, page): return self._compare(self.x, addr, page)
    def CPY(self, addr, page): return self._compare(self.y, addr, page)

    def DEC(self, addr, page):
        result = (self.read(addr) - 1) & 0xFF
        self.write(addr, result)
        self._set_nz(result)
        return 0

    def DEX(self, addr, page):
        self.x = (self.x - 1) & 0xFF
        self._set_nz(self.x)
        return 0

    def DEY(self, addr, page):
        self.y = (self.y - 1) & 0xFF
        self._set_nz(self.y)
        return 0

    def EOR(self, addr, page):
        self.a ^= self.read(addr)
        self._set_nz(self.a)
        return 1 if page else 0

    def INC(self, addr, page):
        result = (self.read(addr) + 1) & 0xFF
        self.write(addr, result)
        self._set_nz(result)
        return 0

    def INX(self, addr, page):
        self.x = (self.x + 1) & 0xFF
        self._set_nz(self.x)
        return 0

    def INY(self, addr, page):
        self.y = (self.y + 1) & 0xFF
        self._set_nz(self.y)
        return 0

    def JMP(self, addr, page):
        self.pc = addr
        return 0

    def JSR(self, addr, page):
        ret = (self.pc - 1) & 0xFFFF
        self.push((ret >> 8) & 0xFF)
        self.push(ret & 0xFF)
        self.pc = addr
        return 0

    def LDA(self, addr, page):
        self.a = self.read(addr)
        self._set_nz(self.a)
        return 1 if page else 0

    def LDX(self, addr, page):
        self.x = self.read(addr)
        self._set_nz(self.x)
        return 1 if page else 0

    def LDY(self, addr, page):
        self.y = self.read(addr)
        self._set_nz(self.y)
        return 1 if page else 0

    def LSR(self, addr, page):
        if self._acc_mode:
            self.c = self.a & 1
            self.a >>= 1
            self._set_nz(self.a)
        else:
            data = self.read(addr)
            self.c = data & 1
            result = data >> 1
            self.write(addr, result)
            self._set_nz(result)
        return 0

    def NOP(self, addr, page): return 0

    def ORA(self, addr, page):
        self.a |= self.read(addr)
        self._set_nz(self.a)
        return 1 if page else 0

    def PHA(self, addr, page): self.push(self.a); return 0

    def PHP(self, addr, page):
        self.push(self.status | 0x30)  
        return 0

    def PLA(self, addr, page):
        self.a = self.pop()
        self._set_nz(self.a)
        return 0

    def PLP(self, addr, page):
        self.status = self.pop()
        self.u = 1
        return 0

    def ROL(self, addr, page):
        old_c = self.c
        if self._acc_mode:
            self.c = (self.a >> 7) & 1
            self.a = ((self.a << 1) | old_c) & 0xFF
            self._set_nz(self.a)
        else:
            data = self.read(addr)
            self.c = (data >> 7) & 1
            result = ((data << 1) | old_c) & 0xFF
            self.write(addr, result)
            self._set_nz(result)
        return 0

    def ROR(self, addr, page):
        old_c = self.c
        if self._acc_mode:
            self.c = self.a & 1
            self.a = (old_c << 7) | (self.a >> 1)
            self._set_nz(self.a)
        else:
            data = self.read(addr)
            self.c = data & 1
            result = (old_c << 7) | (data >> 1)
            self.write(addr, result)
            self._set_nz(result)
        return 0

    def RTI(self, addr, page):
        self.status = self.pop()
        self.u = 1
        lo = self.pop()
        hi = self.pop()
        self.pc = (hi << 8) | lo
        return 0

    def RTS(self, addr, page):
        lo = self.pop()
        hi = self.pop()
        self.pc = (((hi << 8) | lo) + 1) & 0xFFFF
        return 0

    def SBC(self, addr, page):
        data = self.read(addr) ^ 0xFF
        result = self.a + data + self.c
        self.v = 1 if ((self.a ^ result) & (data ^ result) & 0x80) else 0
        self.c = 1 if result > 0xFF else 0
        self.a = result & 0xFF
        self._set_nz(self.a)
        return 1 if page else 0

    def SEC(self, addr, page): self.c = 1; return 0
    def SED(self, addr, page): self.d = 1; return 0
    def SEI(self, addr, page): self.i = 1; return 0

    def STA(self, addr, page): self.write(addr, self.a); return 0
    def STX(self, addr, page): self.write(addr, self.x); return 0
    def STY(self, addr, page): self.write(addr, self.y); return 0

    def TAX(self, addr, page): self.x = self.a; self._set_nz(self.x); return 0
    def TAY(self, addr, page): self.y = self.a; self._set_nz(self.y); return 0
    def TSX(self, addr, page): self.x = self.sp; self._set_nz(self.x); return 0
    def TXA(self, addr, page): self.a = self.x; self._set_nz(self.a); return 0
    def TXS(self, addr, page): self.sp = self.x; return 0
    def TYA(self, addr, page): self.a = self.y; self._set_nz(self.a); return 0

    def _build_opcode_table(self):
        self.opcodes = {
            0x69: (self.ADC, self.IMM, 2), 0x65: (self.ADC, self.ZPG, 3),
            0x75: (self.ADC, self.ZPX, 4), 0x6D: (self.ADC, self.ABS, 4),
            0x7D: (self.ADC, self.ABX, 4), 0x79: (self.ADC, self.ABY, 4),
            0x61: (self.ADC, self.IZX, 6), 0x71: (self.ADC, self.IZY, 5),

            0x29: (self.AND, self.IMM, 2), 0x25: (self.AND, self.ZPG, 3),
            0x35: (self.AND, self.ZPX, 4), 0x2D: (self.AND, self.ABS, 4),
            0x3D: (self.AND, self.ABX, 4), 0x39: (self.AND, self.ABY, 4),
            0x21: (self.AND, self.IZX, 6), 0x31: (self.AND, self.IZY, 5),

            0x0A: (self.ASL, self.ACC, 2), 0x06: (self.ASL, self.ZPG, 5),
            0x16: (self.ASL, self.ZPX, 6), 0x0E: (self.ASL, self.ABS, 6),
            0x1E: (self.ASL, self.ABX, 7),

            0x90: (self.BCC, self.REL, 2), 0xB0: (self.BCS, self.REL, 2),
            0xF0: (self.BEQ, self.REL, 2), 0x30: (self.BMI, self.REL, 2),
            0xD0: (self.BNE, self.REL, 2), 0x10: (self.BPL, self.REL, 2),
            0x50: (self.BVC, self.REL, 2), 0x70: (self.BVS, self.REL, 2),

            0x24: (self.BIT, self.ZPG, 3), 0x2C: (self.BIT, self.ABS, 4),

            0x00: (self.BRK, self.IMP, 7),

            0x18: (self.CLC, self.IMP, 2), 0xD8: (self.CLD, self.IMP, 2),
            0x58: (self.CLI, self.IMP, 2), 0xB8: (self.CLV, self.IMP, 2),

            0xC9: (self.CMP, self.IMM, 2), 0xC5: (self.CMP, self.ZPG, 3),
            0xD5: (self.CMP, self.ZPX, 4), 0xCD: (self.CMP, self.ABS, 4),
            0xDD: (self.CMP, self.ABX, 4), 0xD9: (self.CMP, self.ABY, 4),
            0xC1: (self.CMP, self.IZX, 6), 0xD1: (self.CMP, self.IZY, 5),

            0xE0: (self.CPX, self.IMM, 2), 0xE4: (self.CPX, self.ZPG, 3),
            0xEC: (self.CPX, self.ABS, 4),

            0xC0: (self.CPY, self.IMM, 2), 0xC4: (self.CPY, self.ZPG, 3),
            0xCC: (self.CPY, self.ABS, 4),

            0xC6: (self.DEC, self.ZPG, 5), 0xD6: (self.DEC, self.ZPX, 6),
            0xCE: (self.DEC, self.ABS, 6), 0xDE: (self.DEC, self.ABX, 7),

            0xCA: (self.DEX, self.IMP, 2), 0x88: (self.DEY, self.IMP, 2),

            0x49: (self.EOR, self.IMM, 2), 0x45: (self.EOR, self.ZPG, 3),
            0x55: (self.EOR, self.ZPX, 4), 0x4D: (self.EOR, self.ABS, 4),
            0x5D: (self.EOR, self.ABX, 4), 0x59: (self.EOR, self.ABY, 4),
            0x41: (self.EOR, self.IZX, 6), 0x51: (self.EOR, self.IZY, 5),

            0xE6: (self.INC, self.ZPG, 5), 0xF6: (self.INC, self.ZPX, 6),
            0xEE: (self.INC, self.ABS, 6), 0xFE: (self.INC, self.ABX, 7),

            0xE8: (self.INX, self.IMP, 2), 0xC8: (self.INY, self.IMP, 2),

            0x4C: (self.JMP, self.ABS, 3), 0x6C: (self.JMP, self.IND, 5),
            0x20: (self.JSR, self.ABS, 6),

            0xA9: (self.LDA, self.IMM, 2), 0xA5: (self.LDA, self.ZPG, 3),
            0xB5: (self.LDA, self.ZPX, 4), 0xAD: (self.LDA, self.ABS, 4),
            0xBD: (self.LDA, self.ABX, 4), 0xB9: (self.LDA, self.ABY, 4),
            0xA1: (self.LDA, self.IZX, 6), 0xB1: (self.LDA, self.IZY, 5),

            0xA2: (self.LDX, self.IMM, 2), 0xA6: (self.LDX, self.ZPG, 3),
            0xB6: (self.LDX, self.ZPY, 4), 0xAE: (self.LDX, self.ABS, 4),
            0xBE: (self.LDX, self.ABY, 4),

            0xA0: (self.LDY, self.IMM, 2), 0xA4: (self.LDY, self.ZPG, 3),
            0xB4: (self.LDY, self.ZPX, 4), 0xAC: (self.LDY, self.ABS, 4),
            0xBC: (self.LDY, self.ABX, 4),

            0x4A: (self.LSR, self.ACC, 2), 0x46: (self.LSR, self.ZPG, 5),
            0x56: (self.LSR, self.ZPX, 6), 0x4E: (self.LSR, self.ABS, 6),
            0x5E: (self.LSR, self.ABX, 7),

            0xEA: (self.NOP, self.IMP, 2),

            0x09: (self.ORA, self.IMM, 2), 0x05: (self.ORA, self.ZPG, 3),
            0x15: (self.ORA, self.ZPX, 4), 0x0D: (self.ORA, self.ABS, 4),
            0x1D: (self.ORA, self.ABX, 4), 0x19: (self.ORA, self.ABY, 4),
            0x01: (self.ORA, self.IZX, 6), 0x11: (self.ORA, self.IZY, 5),

            0x48: (self.PHA, self.IMP, 3), 0x08: (self.PHP, self.IMP, 3),
            0x68: (self.PLA, self.IMP, 4), 0x28: (self.PLP, self.IMP, 4),

            0x2A: (self.ROL, self.ACC, 2), 0x26: (self.ROL, self.ZPG, 5),
            0x36: (self.ROL, self.ZPX, 6), 0x2E: (self.ROL, self.ABS, 6),
            0x3E: (self.ROL, self.ABX, 7),

            0x6A: (self.ROR, self.ACC, 2), 0x66: (self.ROR, self.ZPG, 5),
            0x76: (self.ROR, self.ZPX, 6), 0x6E: (self.ROR, self.ABS, 6),
            0x7E: (self.ROR, self.ABX, 7),

            0x40: (self.RTI, self.IMP, 6), 0x60: (self.RTS, self.IMP, 6),

            0xE9: (self.SBC, self.IMM, 2), 0xE5: (self.SBC, self.ZPG, 3),
            0xF5: (self.SBC, self.ZPX, 4), 0xED: (self.SBC, self.ABS, 4),
            0xFD: (self.SBC, self.ABX, 4), 0xF9: (self.SBC, self.ABY, 4),
            0xE1: (self.SBC, self.IZX, 6), 0xF1: (self.SBC, self.IZY, 5),

            0x38: (self.SEC, self.IMP, 2), 0xF8: (self.SED, self.IMP, 2),
            0x78: (self.SEI, self.IMP, 2),

            0x85: (self.STA, self.ZPG, 3), 0x95: (self.STA, self.ZPX, 4),
            0x8D: (self.STA, self.ABS, 4), 0x9D: (self.STA, self.ABX, 5),
            0x99: (self.STA, self.ABY, 5), 0x81: (self.STA, self.IZX, 6),
            0x91: (self.STA, self.IZY, 6),

            0x86: (self.STX, self.ZPG, 3), 0x96: (self.STX, self.ZPY, 4),
            0x8E: (self.STX, self.ABS, 4),

            0x84: (self.STY, self.ZPG, 3), 0x94: (self.STY, self.ZPX, 4),
            0x8C: (self.STY, self.ABS, 4),

            0xAA: (self.TAX, self.IMP, 2), 0xA8: (self.TAY, self.IMP, 2),
            0xBA: (self.TSX, self.IMP, 2), 0x8A: (self.TXA, self.IMP, 2),
            0x9A: (self.TXS, self.IMP, 2), 0x98: (self.TYA, self.IMP, 2),
        }
