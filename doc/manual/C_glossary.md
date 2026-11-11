# Glossary {#glossary}

The terms of SD cards, eMMC and LiteSDCard used in this manual, in alphabetical order. Each entry
points to the chapter that explains it.

| Term | Meaning |
|---------------------|----------------------------------------------------------------------------------|
| ACMD | Application command: a command sent right after CMD55, which gives the next index another meaning, such as ACMD41 or ACMD6. See [SD cards in a nutshell](#primer-commands) |
| Block | The unit of a data transfer, 512 bytes on every card the BIOS driver uses. See [Data blocks](#primer-blocks) |
| Block2mem | `SDBlock2MemDMA`: the DMA that writes the blocks read from the card into memory. See [DMAs](#dma) |
| `boot.json` | Manifest on the FAT partition that lists the files `sdcardboot` loads and their addresses. See [Software: BIOS, boot and Linux](#software) |
| BIOS driver | `liblitesdcard` in LiteX: initialization, block reads and writes, and the disk of FatFs. See [Software: BIOS, boot and Linux](#software) |
| Bus width | Number of DAT lines used by the data transfers: 1, 4, or 8 on an eMMC. See [Bus width and speed modes](#primer-speed) |
| Busy | The card holds DAT0 low while it works, after an R1b response or a written block. See [Writes](#primer-writes) |
| Card | An SD card, microSD card or eMMC device: the device on the other side of the bus. See [Cards and form factors](#primer-cards) |
| Card clock | The clock the host sends on CLK, made by the clocker from the system clock. See [PHY: clocking and IO](#phy) |
| CCS | Card Capacity Status, bit 30 of the OCR: 1 when the card takes block numbers, 0 when it takes byte addresses. See [Capacity and addressing](#primer-capacity) |
| CID | Card Identification register, 128 bits: manufacturer, product name, serial number. See [Card registers](#primer-registers) |
| Clocker | `SDPHYClocker`: the divider that makes the card clock and the strobe of each card clock cycle. See [PHY: clocking and IO](#phy) |
| CMD line | The bidirectional line that carries the commands and the responses. See [The bus](#primer-bus) |
| Command | A 48-bit frame sent by the host on CMD: start bit, direction, 6-bit index, 32-bit argument, CRC7, end bit. See [Commands](#primer-commands) |
| Core | `SDCore`: frames the commands, checks the responses and moves the data streams. See [Core: commands, responses, CRC](#core) |
| CRC status token | The 3 bits the card returns on DAT0 after a written block: `010` accepted, `101` CRC error, `110` write error. See [Writes](#primer-writes) |
| CRC7 | The 7-bit CRC of a command and of most responses. See [CRC generators](#core-crc) |
| CRC16 | The 16-bit CRC computed on each DAT line of a block. See [CRC generators](#core-crc) |
| CSD | Card Specific Data register, 128 bits: capacity, block sizes and timings. See [Card registers](#primer-registers) |
| DAT lines | The data lines DAT0 to DAT3, or DAT0 to DAT7 on an eMMC. See [The bus](#primer-bus) |
| Divider | The 9-bit value of `clocker_divider`; the card clock is the system clock divided by it, rounded up to even. See [Card clock and divider](#perf-divider) |
| eMMC | A soldered device with an MMC interface, an 8-bit bus and an EXT_CSD register; it answers CMD1 instead of CMD8. See [eMMC differences](#primer-emmc) |
| Emulator | `SDEmulator`: a Verilog card model with one 512-byte buffer by default, or a block-addressed store, for simulation or an FPGA. See [The SD card emulator](#emulator) |
| EXT_CSD | The 512-byte extended register of an eMMC; CMD6 writes its bytes, such as the bus width and the timing. See [eMMC differences](#primer-emmc) |
| FatFs | The FAT file system library of the LiteX BIOS; it reads the card through the BIOS driver. See [Software: BIOS, boot and Linux](#software) |
| HCS | Host Capacity Support, bit 30 of the ACMD41 argument: the host accepts high-capacity cards. See [Initialization](#primer-init) |
| High speed | The 50 MHz mode of an SD card, selected with CMD6, and the timing of an eMMC selected with HS_TIMING, up to 52 MHz. See [Bus width and speed modes](#primer-speed) |
| Host | The FPGA side of the bus: LiteSDCard and its software. See [The bus](#primer-bus) |
| `litex_mmc` | The Linux driver of LiteSDCard, upstream in the kernel, bound by `compatible = "litex,mmc"`. See [Software: BIOS, boot and Linux](#software) |
| Mem2block | `SDMem2BlockDMA`: the DMA that reads from memory the blocks to write to the card. See [DMAs](#dma) |
| Nac | The access time of a read: the clocks between the end of a command and the start of the first data block. See [Data blocks](#primer-blocks) |
| OCR | Operation Conditions Register, 32 bits: voltage window, CCS and the power-up done bit 31. See [Card registers](#primer-registers) |
| PHY | `SDPHY`: the clocker, the command and data engines and the IO of the pads. See [PHY: clocking and IO](#phy) |
| R1, R1b | The 48-bit card status response; R1b adds a busy on DAT0. See [Responses](#primer-responses) |
| R2 | The 136-bit response that carries the CID or the CSD. See [Responses](#primer-responses) |
| R3 | The 48-bit response that carries the OCR, without a valid CRC7. See [Responses](#primer-responses) |
| R6, R7 | The responses of CMD3 (the RCA) and of CMD8 (the voltage check). See [Responses](#primer-responses) |
| RCA | Relative Card Address, 16 bits: published by an SD card with CMD3, assigned by the host to an eMMC. See [Initialization](#primer-init) |
| Response | The frame a card sends on CMD after a command: 48 bits, or 136 bits for R2. See [Responses](#primer-responses) |
| SCR | SD Configuration Register, 64 bits, read with ACMD51: supported bus widths and commands. See [Card registers](#primer-registers) |
| SD mode | The native protocol of the card on CMD and DAT, with CRCs, used by LiteSDCard. See [SD mode and SPI mode](#primer-modes) |
| `sdcardboot` | The BIOS boot method that loads `boot.json` or `boot.bin` from the FAT partition. See [Software: BIOS, boot and Linux](#software) |
| SDSC, SDHC, SDXC | Standard (up to 2 GB, byte addresses), high and extended capacity (block addresses) cards. See [Capacity and addressing](#primer-capacity) |
| SPI mode | The simpler protocol of a card on four SPI pins; LiteX drives it with `add_spi_sdcard`, not with LiteSDCard. See [SD mode and SPI mode](#primer-modes) |
| UHS-I | The 1.8 V bus modes (SDR12 to SDR104, DDR50), which need a voltage switch (CMD11) and, at the highest clocks, tuning; not implemented. See [Bus width and speed modes](#primer-speed) |
