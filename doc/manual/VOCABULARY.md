# Vocabulary of the LiteSDCard manual

Project-specific writing rules, completing the generic `STYLE.md` of the manual kit.

## Names of the parts

- *LiteSDCard* or *the project* is the whole repository; *the core* is `SDCore` alone (commands,
  responses, CRC7, read FIFO, events). Never "the core" for the whole project.
- *the PHY* is `SDPHY` and its sub-blocks: *the clocker* (`SDPHYClocker`), *the init block*
  (`SDPHYInit`), *the command writer* and *command reader* (`SDPHYCMDW`, `SDPHYCMDR`), *the data
  writer* and *data reader* (`SDPHYDATAW`, `SDPHYDATAR`); together the last four are *the engines*.
- *block2mem* and *mem2block* are the two DMAs (`SDBlock2MemDMA`, `SDMem2BlockDMA`), in code
  font only when the class or the register prefix is meant.
- *the emulator* is `SDEmulator` and its Verilog card model; *the generator* is `litesdcard_gen`
  (`litesdcard/gen.py`); *the BIST* is the frontend of `litesdcard/frontend/bist.py`.
- *the BIOS driver* is `liblitesdcard` of LiteX (`litex/soc/software/liblitesdcard/sdcard.c`);
  *the Linux driver* is `litex_mmc`; both live outside this repository.
- *register* for a control and status register of the SoC, never "CSR" in prose; *card register*
  for OCR, CID, CSD and the others inside the card.

## Protocol names

- *card* means an SD card or an eMMC device; *SD card* and *eMMC* when the difference matters
  (never "SDCard" in prose, only in code names). *host* is the FPGA side.
- *SD mode* and *SPI mode* for the two bus protocols.
- *CMD line*, *DAT lines* (DAT0 to DAT3, DAT0 to DAT7 on eMMC), *card clock* (the clock the host
  sends on the CLK pin; never "SD clk" in prose) and *system clock* (`sys`).
- *command*: the 48-bit frame from the host; *response*: the frame from the card, named R1, R1b,
  R2, R3, R6, R7 as in the specification. Commands are CMD*n* and application commands ACMD*n*,
  with no space (CMD17, ACMD41).
- *block*: one data unit with its CRC, 512 bytes unless stated; *bus width*: 1, 4 or 8 bits.
- *CRC7*, *CRC16*, *CRC status token*, *busy* (the card holding DAT0 low).
- Card registers in capitals: OCR, CID, CSD, SCR, RCA, EXT_CSD; their fields in capitals as in
  the specification (CCS, HCS, XPC, C_SIZE, BUS_WIDTH, HS_TIMING).
- Card families: SDSC, SDHC, SDXC; speed modes: *default speed* and *high speed*; UHS-I only to say
  what is not implemented.
- *divider* is the clocker register that sets the card clock.
- Cite the SD specification as "SD Physical Layer Simplified Specification section 4.7" and eMMC
  as "JEDEC JESD84", without section numbers unless sure; never by page.

## Placeholders

- `<target>` is a LiteX-Boards target script name without `.py` (`digilent_arty`); defined once
  in the Conventions of the front matter.

## Hardware names

- Boards as LiteX-Boards names them, in prose: Arty A7, Genesys2, TrellisBoard, ECPIX-5, ULX3S,
  Efinix Ti375 C529 Dev Kit. Adapter: Digilent Pmod MicroSD (`PmodSDCard`).
- FPGA families: Xilinx 7-Series, UltraScale and UltraScale+, Lattice ECP5 and NX, Intel/Altera
  (Cyclone, MAX 10, Agilex), Gowin, Efinix, Cologne Chip GateMate.
