# Python NES Emulator

A simple Nintendo Entertainment System emulator written in Python. It uses
Pygame for the display and audio, NumPy for frame and sound sample handling,
and includes implementations of the NES CPU, PPU, APU, controller input, and
several common cartridge mappers.

## Features

- iNES (`.nes`) cartridge loading
- 6502 CPU instruction implementation
- PPU rendering at 256x240, scaled 3x
- APU pulse, triangle, noise, and DMC channels
- Controller 1 input
- Horizontal, vertical, single-screen, and four-screen nametable mirroring
- Mapper support:
  - Mapper 0 (NROM)
  - Mapper 1 (MMC1)
  - Mapper 2 (UxROM)
  - Mapper 3 (CNROM)
  - Mapper 4 (MMC3)

## Requirements

- Python 3
- Pygame
- NumPy

## Installation

Clone the repository and install the Python dependencies:

```powershell
git clone https://github.com/AbsoluteZyro/python-nes-emulator.git
cd python-nes-emulator
python -m pip install -r requirements.txt
```

## Running

Pass a valid iNES ROM to `main.py`:

```powershell
python main.py path\to\game.nes
```

The emulator opens at a resolution of 768x720 and targets 60.0988 frames per
second. ROMs and their copyrights are not included in this repository.

## Controls

| NES button | Keyboard |
| --- | --- |
| A | Z |
| B | X |
| Select | Right Shift |
| Start | Enter |
| Up | Up Arrow |
| Down | Down Arrow |
| Left | Left Arrow |
| Right | Right Arrow |

Additional keyboard controls:

| Action | Keyboard |
| --- | --- |
| Reset | R |
| Quit | Escape |

## Project Layout

- `main.py` - application entry point, Pygame display, timing, and audio output
- `cpu.py` - 6502 CPU
- `ppu.py` - picture processing unit and rendering
- `apu.py` - audio processing unit
- `bus.py` - CPU bus and component coordination
- `cartridge.py` - iNES parsing and cartridge mapper implementations
- `controller.py` - controller state and serial reads

## Notes

This is an educational emulator and should not be considered cycle-perfect or
feature-complete. Compatibility depends on the ROM and whether it uses one of
the supported mappers. You must provide your own legally obtained ROM files.