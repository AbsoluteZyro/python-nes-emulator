# NES PPU (Picture Processing Unit)

from cartridge import MIRROR_HORIZONTAL, MIRROR_VERTICAL, MIRROR_SINGLE_LO, MIRROR_SINGLE_HI

# NES master palette (RGB)
PALETTE = [
    (84,84,84),(0,30,116),(8,16,144),(48,0,136),(68,0,100),(92,0,48),(84,4,0),(60,24,0),
    (32,42,0),(8,58,0),(0,64,0),(0,60,0),(0,50,60),(0,0,0),(0,0,0),(0,0,0),
    (152,150,152),(8,76,196),(48,50,236),(92,30,228),(136,20,176),(160,20,100),(152,34,32),(120,60,0),
    (84,90,0),(40,114,0),(8,124,0),(0,118,40),(0,102,120),(0,0,0),(0,0,0),(0,0,0),
    (236,238,236),(76,154,236),(120,124,236),(176,98,236),(228,84,236),(236,88,180),(236,106,100),(212,136,32),
    (160,170,0),(116,196,0),(76,208,32),(56,204,108),(56,180,204),(60,60,60),(0,0,0),(0,0,0),
    (236,238,236),(168,204,236),(188,188,236),(212,178,236),(236,174,236),(236,174,212),(236,180,176),(228,196,144),
    (204,210,120),(180,222,120),(168,226,144),(152,226,180),(160,214,228),(160,162,160),(0,0,0),(0,0,0),
]


class PPU:
    def __init__(self, cartridge):
        self.cart = cartridge

        self.vram    = bytearray(2048)
        self.oam     = bytearray(256)
        self.palette = bytearray(32)
        self.oam_addr = 0

        # Internal registers
        self.v = 0        # current VRAM address (15-bit)
        self.t = 0        # temp VRAM address (15-bit)
        self.x = 0        # fine X scroll (3-bit)
        self.w = 0        # write toggle

        # Control ($2000)
        self.ctrl_nmi        = 0
        self.ctrl_master     = 0
        self.ctrl_sprite_h   = 0   # 0=8x8, 1=8x16
        self.ctrl_bg_table   = 0   # background pattern table
        self.ctrl_spr_table  = 0   # sprite pattern table (8x8 only)
        self.ctrl_inc        = 0   # VRAM increment (0=+1, 1=+32)
        self.ctrl_nt         = 0   # base nametable

        # Mask ($2001)
        self.mask_emph_b     = 0
        self.mask_emph_g     = 0
        self.mask_emph_r     = 0
        self.mask_show_spr   = 0
        self.mask_show_bg    = 0
        self.mask_spr_left   = 0
        self.mask_bg_left    = 0
        self.mask_greyscale  = 0

        # Status ($2002)
        self.stat_vblank     = 0
        self.stat_spr0       = 0
        self.stat_spr_over   = 0

        self.scanline   = 0
        self.cycle      = 0
        self.frame_odd  = False
        self.nmi_output = False

        self.bg_next_id   = 0
        self.bg_next_attr = 0
        self.bg_next_lo   = 0
        self.bg_next_hi   = 0

        self.bg_shift_pat_lo  = 0
        self.bg_shift_pat_hi  = 0
        self.bg_shift_attr_lo = 0
        self.bg_shift_attr_hi = 0

        # Sprite evaluation
        self.spr_count     = 0
        self.spr_patterns  = [0] * 8
        self.spr_positions = [0] * 8
        self.spr_priorities= [0] * 8
        self.spr_indices   = [0] * 8

        self.frame_buffer  = bytearray(256 * 240 * 3)
        self.frame_ready   = False
        self._data_buf     = 0
        self.total_cycles  = 0

    # ---- Nametable mirroring ----

    def _nt_addr(self, addr):
        addr &= 0x0FFF
        m = self.cart.mirror
        if m == MIRROR_HORIZONTAL:
            if addr < 0x0400:   return addr & 0x03FF
            elif addr < 0x0800: return addr & 0x03FF
            elif addr < 0x0C00: return 0x0400 + (addr & 0x03FF)
            else:               return 0x0400 + (addr & 0x03FF)
        elif m == MIRROR_VERTICAL:
            return addr & 0x07FF
        elif m == MIRROR_SINGLE_LO:
            return addr & 0x03FF
        else:  # SINGLE_HI / FOUR
            return addr & 0x07FF

    # ---- Bus access ----

    def ppu_read(self, addr):
        addr &= 0x3FFF
        if addr < 0x2000:
            return self.cart.ppu_read(addr)
        elif addr < 0x3F00:
            return self.vram[self._nt_addr(addr)]
        else:
            addr &= 0x1F
            if addr in (0x10, 0x14, 0x18, 0x1C):
                addr &= 0x0F
            return self.palette[addr] & (0x30 if self.mask_greyscale else 0x3F)

    def ppu_write(self, addr, data):
        addr &= 0x3FFF
        if addr < 0x2000:
            self.cart.ppu_write(addr, data)
        elif addr < 0x3F00:
            self.vram[self._nt_addr(addr)] = data
        else:
            addr &= 0x1F
            if addr in (0x10, 0x14, 0x18, 0x1C):
                addr &= 0x0F
            self.palette[addr] = data

    # ---- CPU register access ($2000-$2007) ----

    def cpu_read(self, addr):
        reg = addr & 7
        if reg == 2:   # PPUSTATUS
            data = (self.stat_vblank << 7 | self.stat_spr0 << 6 |
                    self.stat_spr_over << 5) | (self._data_buf & 0x1F)
            self.stat_vblank = 0
            self.w = 0
            return data
        elif reg == 4: # OAMDATA
            return self.oam[self.oam_addr]
        elif reg == 7: # PPUDATA
            data = self._data_buf
            self._data_buf = self.ppu_read(self.v)
            if (self.v & 0x3FFF) >= 0x3F00:
                data = self._data_buf
            self.v = (self.v + (32 if self.ctrl_inc else 1)) & 0x7FFF
            return data
        return 0

    def cpu_write(self, addr, data):
        reg = addr & 7
        if reg == 0:   # PPUCTRL
            self.ctrl_nmi       = (data >> 7) & 1
            self.ctrl_master    = (data >> 6) & 1
            self.ctrl_sprite_h  = (data >> 5) & 1
            self.ctrl_bg_table  = (data >> 4) & 1
            self.ctrl_spr_table = (data >> 3) & 1
            self.ctrl_inc       = (data >> 2) & 1
            self.ctrl_nt        = data & 3
            self.t = (self.t & 0x73FF) | ((data & 3) << 10)
        elif reg == 1: # PPUMASK
            self.mask_emph_b    = (data >> 7) & 1
            self.mask_emph_g    = (data >> 6) & 1
            self.mask_emph_r    = (data >> 5) & 1
            self.mask_show_spr  = (data >> 4) & 1
            self.mask_show_bg   = (data >> 3) & 1
            self.mask_spr_left  = (data >> 2) & 1
            self.mask_bg_left   = (data >> 1) & 1
            self.mask_greyscale = data & 1
        elif reg == 3: # OAMADDR
            self.oam_addr = data
        elif reg == 4: # OAMDATA
            self.oam[self.oam_addr] = data
            self.oam_addr = (self.oam_addr + 1) & 0xFF
        elif reg == 5: # PPUSCROLL
            if self.w == 0:
                self.t = (self.t & 0x7FE0) | (data >> 3)
                self.x = data & 7
                self.w = 1
            else:
                self.t = (self.t & 0x0C1F) | ((data & 0x07) << 12) | ((data & 0xF8) << 2)
                self.w = 0
        elif reg == 6: # PPUADDR
            if self.w == 0:
                self.t = (self.t & 0x00FF) | ((data & 0x3F) << 8)
                self.w = 1
            else:
                self.t = (self.t & 0x7F00) | data
                self.v = self.t
                self.w = 0
        elif reg == 7: # PPUDATA
            self.ppu_write(self.v, data)
            self.v = (self.v + (32 if self.ctrl_inc else 1)) & 0x7FFF

    # ---- Internal scroll helpers ----

    def _inc_scroll_x(self):
        if self.mask_show_bg or self.mask_show_spr:
            if (self.v & 0x001F) == 31:
                self.v &= ~0x001F
                self.v ^= 0x0400
            else:
                self.v += 1

    def _inc_scroll_y(self):
        if self.mask_show_bg or self.mask_show_spr:
            if (self.v & 0x7000) != 0x7000:
                self.v += 0x1000
            else:
                self.v &= ~0x7000
                y = (self.v & 0x03E0) >> 5
                if y == 29:
                    y = 0
                    self.v ^= 0x0800
                elif y == 31:
                    y = 0
                else:
                    y += 1
                self.v = (self.v & ~0x03E0) | (y << 5)

    def _transfer_x(self):
        if self.mask_show_bg or self.mask_show_spr:
            self.v = (self.v & ~0x041F) | (self.t & 0x041F)

    def _transfer_y(self):
        if self.mask_show_bg or self.mask_show_spr:
            self.v = (self.v & ~0x7BE0) | (self.t & 0x7BE0)

    # ---- Background fetch helpers ----

    def _fetch_nt(self):
        self.bg_next_id = self.ppu_read(0x2000 | (self.v & 0x0FFF))

    def _fetch_attr(self):
        addr = (0x23C0 | (self.v & 0x0C00) |
                ((self.v >> 4) & 0x38) | ((self.v >> 2) & 0x07))
        shift = ((self.v >> 4) & 4) | (self.v & 2)
        self.bg_next_attr = (self.ppu_read(addr) >> shift) & 3

    def _fetch_lo(self):
        y = (self.v >> 12) & 7
        addr = (self.ctrl_bg_table << 12) | (self.bg_next_id << 4) | y
        self.bg_next_lo = self.ppu_read(addr)

    def _fetch_hi(self):
        y = (self.v >> 12) & 7
        addr = (self.ctrl_bg_table << 12) | (self.bg_next_id << 4) | 0x08 | y
        self.bg_next_hi = self.ppu_read(addr)

    def _load_bg_shifters(self):
        self.bg_shift_pat_lo  = (self.bg_shift_pat_lo  & 0xFF00) | self.bg_next_lo
        self.bg_shift_pat_hi  = (self.bg_shift_pat_hi  & 0xFF00) | self.bg_next_hi
        self.bg_shift_attr_lo = (self.bg_shift_attr_lo & 0xFF00) | (0xFF if self.bg_next_attr & 1 else 0)
        self.bg_shift_attr_hi = (self.bg_shift_attr_hi & 0xFF00) | (0xFF if self.bg_next_attr & 2 else 0)

    def _update_shifters(self):
        if self.mask_show_bg:
            self.bg_shift_pat_lo  = (self.bg_shift_pat_lo  << 1) & 0xFFFF
            self.bg_shift_pat_hi  = (self.bg_shift_pat_hi  << 1) & 0xFFFF
            self.bg_shift_attr_lo = (self.bg_shift_attr_lo << 1) & 0xFFFF
            self.bg_shift_attr_hi = (self.bg_shift_attr_hi << 1) & 0xFFFF

    # ---- Sprite evaluation ----

    def _sprite_eval(self):
        self.spr_count = 0
        self.stat_spr0 = 0
        for i in range(64):
            y    = self.oam[i * 4]
            tile = self.oam[i * 4 + 1]
            attr = self.oam[i * 4 + 2]
            x    = self.oam[i * 4 + 3]
            diff = self.scanline - y
            h = 16 if self.ctrl_sprite_h else 8
            if 0 <= diff < h:
                if self.spr_count < 8:
                    if i == 0:
                        self.stat_spr0 = 1
                    flip_v = bool(attr & 0x80)
                    flip_h = bool(attr & 0x40)
                    row = diff if not flip_v else (h - 1 - diff)
                    if self.ctrl_sprite_h:
                        table = (tile & 1) << 12
                        tile_idx = (tile & ~1) + (1 if row >= 8 else 0)
                        row &= 7
                    else:
                        table = self.ctrl_spr_table << 12
                        tile_idx = tile
                    addr_lo = table | (tile_idx << 4) | row
                    addr_hi = addr_lo + 8
                    lo = self.ppu_read(addr_lo)
                    hi = self.ppu_read(addr_hi)
                    if flip_h:
                        lo = int('{:08b}'.format(lo)[::-1], 2)
                        hi = int('{:08b}'.format(hi)[::-1], 2)
                    self.spr_patterns[self.spr_count]  = (hi << 8) | lo
                    self.spr_positions[self.spr_count] = x
                    self.spr_priorities[self.spr_count]= (attr >> 5) & 1
                    self.spr_indices[self.spr_count]   = (attr & 3)
                    self.spr_count += 1
                else:
                    self.stat_spr_over = 1

    # ---- Main clock ----

    def clock(self):
        self.nmi_output = False

        if self.scanline < 240 or self.scanline == 261:
            # Pre-render scanline: clear vblank/sprite flags
            if self.scanline == 261 and self.cycle == 1:
                self.stat_vblank = 0
                self.stat_spr_over = 0

            # Background fetch pipeline
            if (2 <= self.cycle <= 257) or (321 <= self.cycle <= 337):
                self._update_shifters()
                phase = (self.cycle - 1) & 7
                if phase == 0:
                    self._load_bg_shifters()
                    self._fetch_nt()
                elif phase == 2:
                    self._fetch_attr()
                elif phase == 4:
                    self._fetch_lo()
                elif phase == 6:
                    self._fetch_hi()
                elif phase == 7:
                    self._inc_scroll_x()

            if self.cycle == 256:
                self._inc_scroll_y()
            if self.cycle == 257:
                self._load_bg_shifters()
                self._transfer_x()

            # Pre-render: copy Y address from T to V
            if self.scanline == 261 and 280 <= self.cycle <= 304:
                self._transfer_y()

        # Visible scanline: sprite evaluation
        if self.scanline < 240 and self.cycle == 257:
            self._sprite_eval()

        # VBlank
        if self.scanline == 241 and self.cycle == 1:
            self.stat_vblank = 1
            if self.ctrl_nmi:
                self.nmi_output = True
            self.frame_ready = True

        # Pixel output
        if 0 <= self.scanline < 240 and 1 <= self.cycle <= 256:
            px = self.cycle - 1
            py = self.scanline

            # Background pixel
            bg_pixel = bg_pal = 0
            if self.mask_show_bg:
                bit = 0x8000 >> self.x
                bg_pixel = ((1 if self.bg_shift_pat_hi & bit else 0) << 1 |
                             (1 if self.bg_shift_pat_lo & bit else 0))
                bg_pal   = ((1 if self.bg_shift_attr_hi & bit else 0) << 1 |
                             (1 if self.bg_shift_attr_lo & bit else 0))
                if not self.mask_bg_left and px < 8:
                    bg_pixel = bg_pal = 0

            # Sprite pixel
            spr_pixel = spr_pal = 0
            spr_priority = 0
            spr_is_zero  = False
            if self.mask_show_spr:
                for s in range(self.spr_count):
                    diff = px - self.spr_positions[s]
                    if 0 <= diff < 8:
                        bit = 0x80 >> diff
                        lo  = 1 if (self.spr_patterns[s] & bit) else 0
                        hi  = 1 if (self.spr_patterns[s] & (bit << 8)) else 0
                        spr_pixel = (hi << 1) | lo
                        if spr_pixel != 0:
                            spr_pal      = self.spr_indices[s] + 4
                            spr_priority = self.spr_priorities[s]
                            spr_is_zero  = (s == 0 and self.stat_spr0)
                            break
                if not self.mask_spr_left and px < 8:
                    spr_pixel = spr_pal = 0

            # Pixel priority
            if bg_pixel == 0 and spr_pixel == 0:
                pal_idx = 0
            elif bg_pixel == 0:
                pal_idx = spr_pal * 4 + spr_pixel
            elif spr_pixel == 0:
                pal_idx = bg_pal * 4 + bg_pixel
            else:
                if spr_is_zero and px < 255:
                    self.stat_spr0 = 1
                pal_idx = (bg_pal * 4 + bg_pixel) if spr_priority else (spr_pal * 4 + spr_pixel)

            color = PALETTE[self.ppu_read(0x3F00 + pal_idx) & 0x3F]
            idx = (py * 256 + px) * 3
            self.frame_buffer[idx]     = color[0]
            self.frame_buffer[idx + 1] = color[1]
            self.frame_buffer[idx + 2] = color[2]

        # Advance cycle/scanline
        self.total_cycles += 1
        self.cycle += 1
        if self.cycle > 340:
            self.cycle = 0
            self.scanline += 1
            if self.scanline > 261:
                self.scanline = 0
                self.frame_odd = not self.frame_odd
                # Skip cycle 0 on odd frames when rendering
                if self.frame_odd and (self.mask_show_bg or self.mask_show_spr):
                    self.cycle = 1

    # ---- DMA ----

    def dma_write(self, page, bus_read):
        base = page << 8
        for i in range(256):
            self.oam[(self.oam_addr + i) & 0xFF] = bus_read(base + i)
