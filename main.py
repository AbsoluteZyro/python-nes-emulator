

import sys
import time
import pygame
import numpy as np

from cartridge import Cartridge
from bus import Bus
from controller import (BTN_A, BTN_B, BTN_SELECT, BTN_START,
                        BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT)

SCREEN_W  = 256
SCREEN_H  = 240
SCALE     = 3
FPS_TARGET = 60.0988
SAMPLE_RATE = 44100
AUDIO_BUF   = 512

KEYMAP = {
    pygame.K_z:      (1, BTN_A),
    pygame.K_x:      (1, BTN_B),
    pygame.K_RSHIFT: (1, BTN_SELECT),
    pygame.K_RETURN: (1, BTN_START),
    pygame.K_UP:     (1, BTN_UP),
    pygame.K_DOWN:   (1, BTN_DOWN),
    pygame.K_LEFT:   (1, BTN_LEFT),
    pygame.K_RIGHT:  (1, BTN_RIGHT),
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <rom.nes>")
        sys.exit(1)

    rom_path = sys.argv[1]

    try:
        cart = Cartridge(rom_path)
    except Exception as e:
        print(f"Failed to load ROM: {e}")
        sys.exit(1)

    print(f"Loaded: {rom_path}")
    print(f"Mapper: {cart.mapper_id}  PRG: {len(cart.prg_rom)//1024}KB  "
          f"CHR: {len(cart.chr_rom)//1024}KB  Mirror: {cart.mirror}")

    bus = Bus(cart)
    bus.reset()

    pygame.init()
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, AUDIO_BUF)
    pygame.mixer.init()

    screen = pygame.display.set_mode((SCREEN_W * SCALE, SCREEN_H * SCALE))
    pygame.display.set_caption("NES Emulator")
    clock  = pygame.time.Clock()

    audio_enabled = pygame.mixer.get_init() is not None
    if audio_enabled:
        pygame.mixer.set_num_channels(1)
        channel = pygame.mixer.Channel(0)
        audio_buf = np.array([], dtype=np.float32)

    frame_duration = 1.0 / FPS_TARGET
    last_time = time.perf_counter()

    running = True
    while running:
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    bus.reset()
                elif event.key in KEYMAP:
                    port, btn = KEYMAP[event.key]
                    (bus.controller1 if port == 1 else bus.controller2).set_button(btn, True)
            elif event.type == pygame.KEYUP:
                if event.key in KEYMAP:
                    port, btn = KEYMAP[event.key]
                    (bus.controller1 if port == 1 else bus.controller2).set_button(btn, False)

        
        while not bus.frame_ready:
            bus.clock()

        frame_buf = bus.consume_frame()

        
        surface = pygame.surfarray.make_surface(
            np.frombuffer(frame_buf, dtype=np.uint8)
            .reshape((SCREEN_H, SCREEN_W, 3))
            .swapaxes(0, 1)
        )
        scaled = pygame.transform.scale(surface, (SCREEN_W * SCALE, SCREEN_H * SCALE))
        screen.blit(scaled, (0, 0))
        pygame.display.flip()

        
        if audio_enabled:
            samples = bus.apu.get_samples()
            if samples:
                new_s = np.array(samples, dtype=np.float32)
                audio_buf = np.concatenate([audio_buf, new_s])
            
            if len(audio_buf) >= AUDIO_BUF and not channel.get_busy():
                mono = (audio_buf[:AUDIO_BUF] * 32767).astype(np.int16)
                audio_buf = audio_buf[AUDIO_BUF:]
                _, _, channels = pygame.mixer.get_init()
                chunk = np.column_stack([mono, mono]) if channels == 2 else mono
                sound = pygame.sndarray.make_sound(chunk)
                channel.play(sound)

        
        now = time.perf_counter()
        elapsed = now - last_time
        sleep_for = frame_duration - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)
        last_time = time.perf_counter()

        fps = 1.0 / max(elapsed, 1e-9)
        pygame.display.set_caption(f"NES Emulator  |  {fps:.1f} FPS")

    pygame.quit()


if __name__ == "__main__":
    main()
