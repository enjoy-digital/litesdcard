# AGENTS.md: LiteSDCard

SD card core for LiteX: PHY (generic and vendor IOs), core (commands, CRC), block2mem/mem2block DMA,
emulator, standalone generator; the LiteX BIOS boots from it.

Read the LiteX agent page first: https://github.com/enjoy-digital/litex/wiki/LiteX-for-AI-Agents (framework map, conventions, how to
verify a change, contribute back). Index of the whole wiki for agents: https://github.com/enjoy-digital/litex/wiki/llms.txt.

## Where things are

- `litesdcard/phy.py`, `core.py`, `crc.py`, `frontend/` (DMA); `litesdcard/emulator/`: SD card emulator (simulation).
- `litesdcard/gen.py` (`litesdcard_gen`): standalone core; `bench/`: hardware benches (Arty, Genesys2, TrellisBoard, simulation).
- Software side: LiteX `litex/soc/software/liblitesdcard/` (BIOS init, read/write, boot).

## Verify a change

```sh
python3 -m pytest -v                                                # what CI runs
litex_sim --with-sdcard                                             # SD card model in simulation
```

- Gateware and BIOS (`liblitesdcard`) change together: test the BIOS boot path (`sdcardboot`) when
  touching commands or DMA.
- Cards differ (SDSC/SDHC, speed modes): say which cards were used on hardware.

## Rules

- Style: https://github.com/enjoy-digital/litex/blob/master/doc/coding_style.md (match the
  surrounding file; `module: Description of the change.` commit titles; one change per commit).
- Never edit generated files (`build/`, `csr.h`, `csr.csv`, the Verilog): change the Python.
- One topic per pull request, from the default development branch, with what was tested and on
  which hardware; say that an agent wrote it and who supervised. Do not rename options or
  reformat unrelated code.
- Hardware: never flash a board or write its SPI flash unless the user asked; `--load` (volatile)
  is the default for experiments.

## Debug on hardware

Method: https://github.com/enjoy-digital/litex/wiki/Debug-A-SoC-On-Hardware (check the link and `--ident` first, registers before
traces, narrow LiteScope captures). `litex_mcp` gives the same loop as MCP tools (CSRs by name,
LiteScope captures, builds with parsed timing, simulation): https://github.com/enjoy-digital/litex/wiki/LiteX-for-AI-Agents#drive-a-soc-through-mcp.
