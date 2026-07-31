# VBIOS: structure, versions and DEVINIT

**What this page covers.** The layout of the CMP 170HX SPI ROM image, how to dump it without
bricking the card, what lives in each region, which parts are cryptographically protected and
which are not, what DEVINIT is and what it does (and does not) control, the per-batch version
inventory, and a ranked list of what can and cannot be modified.

**The headline result: the community unlock does not touch the VBIOS at all.** The shipping
`cmpunlocker` tool never reads, writes, flashes or parses the ROM. There is no `nvflash`, no SPI
access and no image handling anywhere in the repository; the whole tool is six kernel-module
patches plus `install.sh` and `remove.sh`. A whole-word search of the shipping tree for
*flash*, *nvflash*, *spi*, *rom* and *vbios* returns no hits at all; the only substring matches
are incidental, such as "from" inside the `remove.sh` completion banner. The unlock happens at runtime, inside the patched GSP boot path. See
[how the unlock works](../unlock/how-it-works.md).

The second headline: **the entire deliberate VBIOS-level restriction on this card is seven
bytes.** Two bytes of CFG1 strap-4 addressing (tier `44` to `66`, which controls HBM address
depth, 12 versus 14 row bits, and 2 versus 8 GB addressable per HBM2 stack) plus five bytes of PCIe
speed DEVINIT spread across three sites. Both sit inside the MAC-verified range, and both
therefore need a key nobody has. Everything else that differs between a 170HX ROM and an A100
ROM is scattered device-ID references and per-build training calibration, neither of which is
restriction-related.

---

## Quick orientation

| Question | Answer |
|---|---|
| Production ROM size | 1,044,480 bytes (1020 KB) on every GA100 production dump |
| Magic at offset 0 | `NVGI` |
| Runtime read aperture | NV_PROM at BAR0 + `0x300000` |
| Cryptographically protected range (170HX 250 W) | `0x2200`-`0x43A00` |
| Protection type | Symmetric MAC (Davies-Meyer hash + AES-KDF) keyed on csecret(2), **not** an RSA image signature |
| Freely modifiable | `0x43A00` to end of image (unsigned FwSec tail, padding, backup mirror, InfoROM) |
| Does VBIOS version affect the unlock? | No |
| Can a modified image be flashed? | Not with `nvflash`/`omgvflash`/`nvflashk`. Unsigned-tail edits need a CH341A |

---

## Dumping the VBIOS

> [!CAUTION]
> **Always dump before you touch anything**
>
> A failed flash or a bad image is recoverable in the large majority of cases **only if a
> stock ROM was saved first**. Standing advice from the people who have bricked and recovered
> these cards: keep the stock dump, and have an external SPI programmer on hand *before*
> touching the NVGI region. One researcher stated "if I corrupt NVGI there is no recovery
> path at all" and self-corrected within one minute: a hardware SPI programmer makes it
> recoverable. An `NV_PROM` MMIO dump is considered an adequate fallback image.
> See [recovery](../procedures/recovery.md).

There are three dump paths. They produce different byte ranges and have different failure modes.

| Method | Range captured | Needs | Risk | Notes |
|---|---|---|---|---|
| `nvflash --save` | 1020 KB (`0x00000`-`0xFF000`) | Driver bound, root | Low | Standard route. On the 170HX this window **does** include the license region at `0xFE000`; on the A100 it does not, because the A100 license TOC is at `0xFF000` |
| NV_PROM MMIO readback | 1,044,480 B from BAR0 + `0x300000` | Root, BAR0 mapping | Very low, read-only | The card's own view of the ROM. Used by the clean-room `ga100_topology_report.py` tooling. Can show `0xFF` where an SPI dump would show content (see the caveat below) |
| CH341A + SOIC clip | Whole SPI part | Cooler removal, repaste | Physical | The only path that can *write* an edited image. Stock cards are hardware write-protected |

### Identify the card and its VBIOS first

```bash
lspci -nn -d 10de: | grep -i GA100
# 0d:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)

nvidia-smi --query-gpu=vbios_version,pci.device_id,pci.sub_device_id,memory.total \
           --format=csv
```

`10de:20c2` is the 8 GB SKU, `10de:2082` the 10 GB SKU. See
[board and variants](board-and-variants.md) for the full identification matrix.

### `nvflash` save

```bash
sudo nvflash64 --save stock_$(date +%F)_$(hostname).rom
sha256sum stock_*.rom
```

### NV_PROM readback over BAR0

The SPI flash is readable at runtime through the NV_PROM aperture at **BAR0 + `0x300000`**,
1,044,480 bytes, first four bytes `NVGI`. The aperture base was derived from the FWSEC
disassembly.

```python
#!/usr/bin/env python3
# Read-only NV_PROM dump. Root required. Replace the BDF with your card's.
import mmap, os

BDF   = "0000:0d:00.0"
BAR0  = f"/sys/bus/pci/devices/{BDF}/resource0"
PROM  = 0x300000          # NV_PROM aperture offset within BAR0
SIZE  = 1044480           # 1020 KiB

fd = os.open(BAR0, os.O_RDONLY)
m  = mmap.mmap(fd, PROM + SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
rom = m[PROM:PROM + SIZE]
assert rom[:4] == b"NVGI", f"bad magic: {rom[:4]!r}"
open("vbios_prom.rom", "wb").write(rom)
print(f"wrote {len(rom)} bytes")
```

> [!WARNING]
> **MMIO readback is not always identical to an SPI dump**
>
> On a Drive A100 the NV_PROM readback showed all `0xFF` at both `0xFE000` and `0xFF000`.
> Whether that region is genuinely empty on that part or whether the TOC structure simply does
> not survive the NV_PROM path is unresolved. Anyone surveying license regions by MMIO should
> confirm with an SPI dump before concluding a region is blank.

### CH341A dump, and verifying it

```bash
# Two independent reads, compared. Never trust a single clip read.
flashrom -p ch341a_spi -r spi_dump_1.rom
flashrom -p ch341a_spi -r spi_dump_2.rom
cmp spi_dump_1.rom spi_dump_2.rom && echo "clip contact is good"
```

On stock cards the SPI flash is hardware write-protected: the dumped status registers read
`00000000 (0x00)`, `01000000 (0x40)`, `11111111 (0xFF)`. One tester defeated the protection and
completed a flash within ten minutes of hitting it, so this is an obstacle rather than a wall.

> [!CAUTION]
> **Write-protect before powering back on**
>
> Flashing failure `0xBADF3000`, with the board unable to read flash, is caused by **not**
> re-enabling SPI write protection before power-on. Recovery is to reflash the SOIC directly
> with a chip clip and then set write protection. The related symptom is an RM init adapter
> failure. There is no OS-level flash path for this board.

### SKU and integrity fingerprint

Two truncated SHA-256 values over fixed ranges act as a cheap SKU and integrity check. Both
pairs are byte-identical across every image checked of the matching SKU, so a mismatch means the
VBIOS differs in code, not merely in per-unit data.

```bash
IFR()  { dd if="$1" iflag=skip_bytes,count_bytes skip=0        count=$((0x1000))          status=none | sha256sum | cut -c1-16; }
FW()   { dd if="$1" iflag=skip_bytes,count_bytes skip=$((0x1200)) count=$((0xC1000-0x1200)) status=none | sha256sum | cut -c1-16; }
echo "IFR      $(IFR vbios_prom.rom)"
echo "FIRMWARE $(FW  vbios_prom.rom)"
```

| SKU | IFR `0x000000`-`0x001000` | FIRMWARE `0x001200`-`0x0C1000` |
|---|---|---|
| 10 GB (`0x2082`) | `3ca3d24230d6800f` | `8c4e1344c51b0940` |
| 8 GB (`0x20C2`) | `2ff19960f9175320` | `e2c91c1808ae2759` |

The assignment above is adjudicated three reports to one; the single outlier attaches the 8 GB
pair to 10 GB images and is treated as a transcription slip. Posting both SKUs' outputs side by
side from one run of the topology tool would close it.

---

## Region map

The published analysis calls this a 13-region map (content regions only). Expanded here to
include padding, the mirror and the InfoROM. Sizes are from the 170HX 250 W images; "signed"
means inside the `0x2200`-`0x43A00` MAC-verified range.

| Offset range | Contents | Size | Signed |
|---|---|---|---|
| `0x00000`-`0x02200` | NVGI header + RFRD manifest, cleartext | 8.5 KB | no (below signed start) |
| `0x02200`-`0x05E00` | PciAt region, BIT tokens, PERF_PTRS | 15.0 KiB | **yes** |
| `0x05E00`-`0x0C700` | FwSec headers, VN images 1 and 2, NPDS/NPDE | 27 KB | **yes** |
| `0x0C700`-`0x0C800` | NPDS/NPDE headers | 256 B | **yes** |
| `0x0C800`-`0x13E00` | Compressed Falcon code, 87 % shared with A100 at delta 0 | 29.5 KB | **yes** |
| `0x13E00`-`0x14A00` | Inter-zone gap, zeros plus headers | 3 KB | **yes** |
| `0x14A00`-`0x20000` | Encrypted firmware region A, AES-128-ECB | 45.5 KB | **yes** |
| `0x20000`-`0x20700` | DMAP cleartext gap, `"Mar  5 2021"` build string plus Falcon fuc5 code | 1.8 KB | **yes** |
| `0x20700`-`0x33800` | Encrypted firmware region B, AES-128-ECB | 76.2 KB | **yes** |
| `0x33800`-`0x41200` | Configuration / DEVINIT-class tables, Shannon entropy 4.5-6.0 | 54.5 KB | **yes** |
| `0x41200`-`0x42A00` | Strap and training tables; CFG1 strap-4 tier byte at `0x41D53` | 6 KB | **yes** |
| `0x42A00`-`0x43A00` | Trailing zeros | 4 KB | **yes** (ends at the boundary) |
| `0x43A00`-`0x47700` | **Unsigned FwSec tail** | 15,616 B | no |
| `0x47700`-`0x60000` | `0xFF` padding | 100 KB | no |
| `0x60000`-`0xA7700` | **Backup mirror of `0x00000`-`0x47700`** | 285 KB | no |
| `0xA7700`-`0xC0000` | `0xFF` padding | 100 KB | no |
| `0xC0000`-end of image | InfoROM (`0xFF000` in a 1020 KB dump, `0xFFFFF` in a full 1 MiB MMIO readback) | 252-256 KB | no |

The `+0x60000` mirror explains every duplicate-table address in the comparison work: if a table
appears at both `0x41D41` and `0xA1D41`, that is one table and its backup copy, not two tables.

> [!NOTE]
> **Two different meanings of 'NVGI region'**
>
> The region map above uses NVGI for `0x00000`-`0x02200`. The 8 GB versus 10 GB diff analysis
> uses NVGI for `0x00000`-`0x05E00`, which is why the four MAC blocks at `0x2CBF`, `0x38BA`,
> `0x595C` and `0x5AF8` are described as being "in NVGI" despite sitting above `0x2200`.

### NPDS body composition

The NPDS body `0x0C700`-`0x43A00` (226,048 bytes) breaks down by entropy class as:

| Class | Share | Detail |
|---|---|---|
| AES-128-ECB ciphertext | 121.7 KB (54 %) | Two regions, one key, 101 internal repeat pairs |
| DEVINIT-class config tables | 54.5 KB (24 %) | Entropy 4.5-6.0, structured cleartext |
| Compressed Falcon code | 29.5 KB (13 %) | 87 % shared with the A100 at delta 0 |
| Headers, gaps, strap tables, padding | 20.3 KB (9 %) | Cleartext |

That 24 % cleartext config band is why DEVINIT bytes can be located by pattern search while the
FwSec firmware cannot.

---

## The RFRD manifest and the signed range

The MAC-verified range is not guessed, it is declared. The manifest at `0x2000` is an **image
layout descriptor**, not a power table.

| Offset | Field | Value / meaning |
|---|---|---|
| `0x2000` | Magic | `"RFRD"` |
| `0x2004` | u16 manifest version | `3` |
| `0x2008` | u32 `pci_option_rom_offset` | Points at the PciAt image start, `0x5E00` |
| `0x200C` | u32 `pci_option_rom_size` | **Size of the MAC-verified range** |
| `0x200D` | (byte) | High byte of `pci_option_rom_size`. Touching it desynchronizes the declared size from the actual signed content, and MAC verification fails |
| `0x201C` | u32 `secondary_base` | `0x2200` |

Signed content always begins at `0x2200`. Per image:

| Image | field_0C | MAC-verified range |
|---|---|---|
| 170HX 8 GB and 10 GB, 250 W | `0x00041800` | `0x2200`-`0x43A00` (268,288 B) |
| 170HX 300 W | `0x00041A00` | `0x2200`-`0x43C00` |
| A100 PCIe 40 GB | `0x00042200` | `0x2200`-`0x44400` |
| Drive A100 32 GB | `0x00058A00` | `0x2200`-`0x5AC00` |

### The range was bounded empirically, not just read

Four physical CH341A flash cycles on 2026-05-08 settled it. Writing `0xFF` padding *outside* the
declared range boots fine and the driver loads normally. Changing a single byte *inside* the
`0x2200`-`0x43A00` window stalls the Booter. The canonical broken-MAC failure signature on GA100
is:

```text
GFW_BOOT = 0x401    (or 0x001)
```

The single-byte test was performed at `0x41D53`, the CFG1 tier byte, which is exactly the byte a
memory unlock would want to change. That is the empirical proof that in-MAC edits are closed.

---

## Cryptography

Two different keys, two different mechanisms, frequently conflated.

| Mechanism | Covers | Key | Status |
|---|---|---|---|
| Symmetric MAC, Davies-Meyer hash + AES-KDF | The `0x2200`-end-of-range content | csecret(2), held in SCP hardware | Forgery requires the key; stated to be extractable only by a DFA hardware attack |
| AES-128-ECB | The two FwSec firmware regions | csecret(6) | Same key across every GA100 variant |
| RSA | Boot ROM authenticating Booter code | NVIDIA production | Separate mechanism, often mistaken for an image signature |

### AES-128-ECB, proven three ways

1. **Cross-ROM re-convergence.** 442 of 2,667 blocks identical between the 170HX and the A100
   across 13 matching runs. CBC can never re-converge after plaintext divergence.
2. **Internal repeated blocks** (the "ECB penguin"). 24 repeated 16-byte pairs within the 170HX
   image, 28 within the A100 image. That rules out CTR.
3. **Strict 16-byte alignment.** Shifting the comparison by one byte drops matches from 442 to
   exactly 0.

**One key encrypts the FwSec blobs across every GA100 variant.** The first four ECB blocks at
`0x14A00` are byte-identical across 170HX 8 GB, 170HX 10 GB, 170HX 300 W and A100 PCIe; the
Drive A100 was added on 2026-05-31 with 30 ECB oracle hits and the same first four blocks,
beginning `b2a93eaa0300209b`. Recovering csecret(6) once would decrypt every GA100 VBIOS in
existence.

### The free known-plaintext oracle

The ROM contains all-`0xFF` plaintext padding blocks, giving:

```text
AES_ECB(key, FF x 16) = 717d1494 eaca317f f1061952 58b38377
```

Repeating ciphertext blocks are at `0x1F8F0` and `0x1FB60` (labelled "end of imem_sec" in ImHex),
21 such padding blocks in ECB region A and 13 in region B, and the pattern reproduces across all
ROM variants. A candidate key can therefore be validated offline in microseconds with no flash
cycle, which is what would make a DFA campaign practical.

The same 128-bit value is separately the marker for **debug-build Falcon IMEM sections encrypted
with the trivial non-secret key `01234567...`**. The recommended workflow for attacking
DEVINIT/FWSEC is: pull a VBIOS from a public collection, search for that padding pattern,
decrypt those IMEM sections with the simple key, then annotate the disassembly. That recipe is a
consistent expert recommendation with no in-channel result posted yet.

> [!NOTE]
> **Open problem**
>
> A separate claim, that "the key is on NVIDIA's own website, I think it's debug #37", was
> never substantiated. Neither the key nor a decrypted production image was ever posted. Treat
> the `01234567...` debug-IMEM recipe as actionable and the "debug #37" claim as unverified.

---

## Tables the image contains

### Inside the signed range (documentation value only)

| Table | Offset | Notes |
|---|---|---|
| BIT table | `0x5EB0`, 16 tokens | Same offset and token count on all six production ROMs |
| FwSec NPDS device ID | in the FwSec headers | Declares `0x2080` (generic GA100) on **all seven** images regardless of their PciAt device ID |
| CFG1 / HBM2 strap table | `0x41D41` (170HX 8 GB, 10 GB, "16 GB"), backup `0xA1D41` | 16 × 32-bit words, **not** word-aligned; secondary `strap_info` table at `0x6A09` |
| CFG1 strap-4 tier byte | `0x41D53` (250 W) / `0x41F53` (300 W) | The two-byte half of the seven-byte restriction |
| PCIe speed DEVINIT | 5 bytes across 3 sites in `0x33800`-`0x41200` | The other half |

Strap-table offsets per image:

| Image | Version | Primary | Backup |
|---|---|---|---|
| 170HX 8 GB and "16 GB" | `92.00.67` | `0x41D41` | `0xA1D41` |
| 170HX 10 GB | `92.00.66` | `0x41D41` | `0xA1D41` |
| 170HX 300 W | `92.00.6D` | `0x41F41` | `0xA1F41` |
| A100 PCIe 40 GB | `92.00.90` | `0x4285A` | `0xA285A` |
| A100 SXM4 40 GB | `92.00.45` | `0x419E5` | `0xA19E5` |
| Drive A100 32 GB | `92.00.A0` | `0x3A7D2` | not determined |

The 300 W ROM places its whole table set exactly `0x200` bytes later than the 250 W siblings.
Leaked GA100 emu/sim ROMs use an entirely different ~230 KB layout with both copies inside the
same image at `0x0864C` and `0x1AD72`, so nothing transplants from them.

**Tier byte decode.** The third byte of each 32-bit strap word is a tier nibble pair taking the
values `44`, `55`, `66`, `77`, encoding 2 GB / intermediate / 8 GB / 16 GB addressable per HBM2
stack. Most entries are the filler pattern `00 90 66 22`. In the 10 GB VBIOS only strap 4 is
nerfed to `44`; in the 8 GB VBIOS straps 5 and 7 are also nerfed. Strap 4 is the physical strap
for 10 GB cards, strap 7 for 8 GB cards. This is the same tier encoding the runtime unlock writes
into CFG1 at `0x009a0204`; see [memory geometry](../unlock/memory-geometry.md).

> [!NOTE]
> **Open problem**
>
> Two incompatible decodes of the per-strap HBM part fields were posted hours apart on
> 2026-07-25. The **vendor and revision fields agree** (Micron/Samsung/Hynix, rev1/rev2/rev3/
> rev6/rev10); the **per-die capacity and stack-height fields do not** (for example strap 5 as
> `Hynix_rev6_16Gb_org0x4` versus `Hynix_rev6_8Gb_4H_org0x4`). The author of the second decode
> noted the publicly circulating forum decoder script "was not fully correct for HBM memory
> configs". The `44`/`66`/`77` capacity mapping is not in dispute. Settling it needs an
> authoritative field-width definition, or one decoded entry matched against a physically
> identified HBM stack part number.

### Outside the signed range (actually editable)

Everything at or above `0x43A00` is unsigned and freely modifiable with an SPI programmer, in
the same class as the `0xFF`-padding test that already booted successfully.

| Item | Offset | Value / detail | Status |
|---|---|---|---|
| Board power limit | `0x45E45`, 3 bytes | `90 D0 03` = 250 W, would become `E0 93 04` for 300 W | Outside the MAC. **Open, untested since 2026-05-09** |
| `NV_FUSE_CTRL_OPT_*` table | `0x47341`, 25 entries | All-zero across 13 probed GA100 cards | Outside. Semantics undetermined |
| `freqDelta` | `0x47177` / `0x47179` | ±1000 on the 8 GB image, `0` on the 10 GB and A100 images | Outside. Explains why core offsetting works only on 8 GB cards |
| M0205 memory training table | `0x467f8` (10 GB) / `0x469f8` (the other image examined) | Header `ver=0x10 hdr=8 entsz=1 cnt=1`, raw `10 08 01 01 10 07 00 00`, 16 strap sub-entries of 7 bytes | Outside |
| InfoROM | `0xC0000` upward | Entirely unsigned | Outside |
| License / HULK TOC | `0xFE000`-`0xFEFFF` | See below | Outside |

The M0205 strap sub-entries are byte-identical between the two images examined, for example
strap0 `0f ff ff ff ff ff ff`, strap2 `ff ff ff 0f ff ff ff`, strap4 `ff ff ff ff ff ff 0f`,
strap7 `ff ff 0f ff ff ff ff`, strap9 `ff ff ff ff ff 0f ff`, strap12 `ff 0f ff ff ff ff ff`,
strap14 `ff ff ff ff 0f ff ff`; all odd straps other than 7 and 9 are all-`ff`.

**Derived from the offsets above and the MAC boundary:** every memory-related table read out in
July 2026 (`freqDelta`, M0205, CTRL_OPT) sits above `0x43C00` and is therefore outside every
170HX MAC range, while the CFG1 strap tier table at `0x41D41`/`0x41D53` sits roughly 10 KB below
the boundary and is inside. **That is the clean dividing line: memory timings and clock offsets
are editable in the image; memory capacity straps are not.**

> [!NOTE]
> **Open problem**
>
> Do unsigned-tail memory edits actually take effect? The natural experiment is to write
> `±1000` into `freqDelta` on a 10 GB image (where it is `0`) and see whether core offsetting
> appears. One CH341A cycle on a card with a saved stock dump would answer it. Nobody has
> reported trying.

### Per-strap timing bytes

Recorded values, medium confidence (the dump was re-read and self-corrected by the same
researcher the following day):

| Index | Bytes |
|---|---|
| idx4 (10 GB) | `46 14 41 04 00 00 00 83 ff ff 00 00 ff ff` |
| idx7 (80 GB) | `76 67 aa 00 00 00 00 15 ff ff 02 00 ff ff` |
| idx8 (80 GB) | `86 18 a3 04 00 00 00 87 ff ff 01 00 ff ff` |
| idx10 (80 GB) | `a6 fa a0 00 00 00 00 01 ff ff 03 00 ff ff` |

### License region and the HULK slot

**The 170HX license region is at `0xFE000`-`0xFEFFF`, not `0xFF000`.** That corrected a
community-wide assumption borrowed from the A100. Verified across five separate 170HX dumps
obtained by three methods (three 10 GB dumps, one of them by SPI and one by MMIO, plus two
8 GB dumps). On
every 170HX the top 4 KB at `0xFF000` is all-`0xFF` and unused. It matters because `nvflash` on
the 170HX dumps 1020 KB, so the region *is* inside the nvflash window on this card even though
it is not on an A100.

| Offset | Contents |
|---|---|
| `0xFE000` | 8 zero bytes |
| `0xFE008` | `"LU"` + `00 10 00 00 00 01`: region header, size `0x1000`, version 1 |
| `0xFE010` | Slot table: `"LIC" 01 00 1D 00` (LIC at +0x1D), `"ULF" 1D 00` (unlock flags), `"UPR" 7D 04` (unlock params at +0x47D), `"HLK" ED 04` (HULK cert at +0x4ED), `"ULF" 01 00 60 04` terminator |
| `0xFE48D` | UPR slot header, empty payload |
| `0xFE4FD` | HLK slot header `"HLK" 01 00 60 04`, version 1, flags 0, slot size `0x0460` (1120 B) |
| `0xFE504` | HLK payload, 1113 bytes of capacity, **all zeros on stock 170HX** |

The reasoning is that a pre-built but empty HULK TOC implies FWSECLIC scans the license region
on every boot, since NVIDIA would not ship a fully formed slot table plus a 1120-byte reserved
slot if nothing read it. The corollary is that a forged or production-signed HULK cert at
`0xFE504` would be an unlock path. This has never been demonstrated by instrumenting FWSECLIC.

> [!NOTE]
> **Open problem**
>
> Injecting a HULK cert at `0xFE504`. The slot exists, is 1113 bytes, is all-zero on stock, and
> sits inside the window `nvflash` writes, so no CH341A is needed in principle. Two blockers:
> the same analysis states `nvflash` is blocked by FwSecLic write-time verification even for
> unsigned-tail changes, and whether the license region is exempt has never been tested; and
> nobody has a signed cert. Cheapest next step: flash an arbitrary non-zero pattern into the
> HLK payload and see whether the write is accepted at all, which separates "the region is
> writable" from "we need a valid cert".

### InfoROM

Entirely unsigned. Notable tags: `IMG` container header, `BRD` board info / part number, `OBD`
card name, `PPO` power/performance (**empty on all 170HX ROMs**), `BBX` BlackBox telemetry,
`RPR` row remap for HBM RAS, and `ECC` ECC configuration (**A100 only**). Card name strings are
`"NVIDIA-A100-PCIe-40GB"`, `"NVIDIA A100-SXM4-40GB"` and `"CMP 170HX"`.

A live 10 GB card enumerates **17 distinct object types**: APP, BBX, BRD, DEM, IMG, NEN, NVL,
OBD, OCT, OEM, OMS, PPO, ROM, RPR, RRL, SEN, ULF, at versions APP v6, BBX v4 and v6, BRD v2,
DEM v6, IMG v2, NEN v14, NVL v6, OBD v2, OCT v6, OEM v2, OMS v14, PPO v6, ROM v2, RPR v6,
RRL v6, SEN v14, ULF v0. `nvidia-smi` on the same SKU reports Inforom Image Version
`1001.0105.01.02`, OEM Object 2.0, with ECC Object and Power Management Object both N/A,
consistent with `ECC` being A100-only and `PPO` being empty.

> [!WARNING]
> **Do not fingerprint a card by total InfoROM object count**
>
> Totals of 22, 23 and 28 have all been reported and **all are correct**: BBX and DEM are
> telemetry records that accumulate with runtime. Only the 17 distinct types and the per-object
> versions are structurally meaningful.

---

## DEVINIT

DEVINIT is the VBIOS-resident initialisation script that programs GPU registers at boot, before
the driver ever sees the device. On GA100 it lives in the `0x33800`-`0x41200` configuration
region: structured cleartext, entropy 4.5-6.0, which is why its bytes can be located by pattern
search while the encrypted FwSec firmware cannot. **Because that region ends at `0x41200`, well
below the `0x43A00` MAC boundary, every DEVINIT modification breaks the Booter MAC.**

### Where it runs

The closed NVIDIA RM contains an **x86 DEVINIT-script interpreter, symbol `_nv000358rm`**, using
ASCII-opcode dispatch. It reads the strap register `0x101000` at code address `0x264fb1` and
executes VBIOS DEVINIT register writes generically. That is why the L2 decode register
`0x17e2a0` never appears as an immediate anywhere in RM code: its address arrives from the VBIOS
script stream, not from RM. Three registry keys control where DEVINIT runs:

| Registry key | Effect |
|---|---|
| `RMExecuteDevinitOnPmu` | Run DEVINIT on the PMU |
| `RmDisableFbflcnDevinitBoot` | Disable the FBFLCN DEVINIT boot path |
| `RMDevinitBySecureBoot` | Run DEVINIT via secure boot |

Confidence medium: this comes from binary analysis with specific symbols and offsets that has not
been independently reproduced.

### Boot order

```text
NVGI records execute
  -> IFR ucode fetches the FWSEC descriptors and starts FWSEC
  -> FWSEC raises the PLMs
  -> devinit / UDE08 programs all 29 FBPA registers
  -> FBFLCN trains the HBM
```

Two consequences follow directly, and both close off obvious attacks: anything NVGI writes into
MR1/MR2/MR3 is overwritten by DEVINIT moments later using the table values for the boot strap,
and writing PLMs from NVGI is futile because FWSEC re-raises them afterwards. Confidence medium;
this is an ordering argument from firmware analysis, not an empirical test.

### DEVINIT and the PCIe Gen1 lock

The PCIe speed restriction is **5 bytes across 3 DEVINIT sites** (Gen1 versus Gen3/4), all inside
the MAC range. The ROM route is therefore closed for the same reason the memory strap byte is
closed: no csecret(2), no MAC forgery, no boot.

What replaced it is entirely runtime. The unreleased `Gen2`-family branches reach Gen2 (5 GT/s)
by writing PCIe registers from the patched driver, never touching the ROM, giving
`LnkCap max Gen2 0x00456102`, `LnkCap2 0x00000006`, `LnkSta trained Gen2 x4 0x1042` and
`nvidia-smi` cur/max/width `2,2,4`. That is link **speed** only; link **width** is a separate,
purely physical matter. See [PCIe Gen2](../unlock/pcie-gen2.md) and
[the PCIe subsystem](pcie-subsystem.md).

> [!NOTE]
> **Open problem**
>
> Gen3 and Gen4 remain unreached. `FUSE_PCIE_GEN23_DIS` `0x0082057c` and `FUSE_PCIE_GEN3_DIS`
> `0x00820580` both read `0x00000001` on every 170HX probed, alongside `FUSE_PCIE_MAGIC_D`
> `0x00820520` = `0x16680000`, and the supported-speeds vector clips at `0x00000006` even after
> the PHY rate is forced to a Gen3-capable `0x00340036`. Two unresolved questions: whether the
> residual cap is the same DEVINIT bytes replayed or the fuse triple enforced independently
> downstream, and whether the five-byte DEVINIT edit alone would restore Gen4 given a flash
> that could be re-signed. See [Gen3 and Gen4](../frontier/pcie-gen3-gen4.md).

### DEVINIT and ECC

> [!NOTE]
> **The evidence points away from DEVINIT here**
>
> **This VBIOS analysis provides no evidence that DEVINIT controls ECC.** The only ECC-related
> datum in the entire ROM comparison is that the InfoROM `ECC` object is present on the A100 and
> absent on the 170HX. No DEVINIT-side ECC bytes were found anywhere in the 54.5 KB config
> table region. Chat-side theories blaming DEVINIT for the 170HX ECC behaviour are unsupported
> by static analysis. This is a notable absence of evidence rather than a positive finding, so
> confidence is medium.

Corroborating from the silicon side: `FEAT_OVR_ECC_PLM` `0x00823800` reads `0xffffff8f` cold and
gates `0x82380c`, `0x823810` and `0x82382C`. The HS ROP can open it, and **opening it is inert**,
because the ECC-enable readout at `0x823814` is POR/fuse-latched and does not respond to live
override writes; the overrides revert on FLR anyway. The branch named `ecc` contains no ECC code
at all (a single commit, "Fixed dual geometry support"). ECC is fused off with no known lever.
Whether the HBM stacks carry ECC provisioning is only partly answered: the A100 per-FBPA
`CSTATUS_RAMAMOUNT` differential reads as ECC being reserved capacity inside the same stacks, on
one participant's inference rather than a datasheet. See [ECC](../frontier/ecc.md).

### Re-executing DEVINIT at runtime

> [!WARNING]
> **Experimental**
>
> Re-executing DEVINIT at runtime via the PMU **did** change hardware state, on one card, in
> one session. It did not produce more usable memory.

| Register | Before | After |
|---|---|---|
| CFG1 `0x009a0204` | `0x02669000` | `0x22779000` |
| CSTATUS | `0x00000800` | `0x00000800` (unchanged) |
| LMR `0x00100ce0` | `0x0000028a` | `0x0000028a` (unchanged) |
| `0x9a038c` | `0xa7` | `0xa6` |
| `0x9a0330` | `0x00100093` | `0x0010009c` |
| `0x9a0334` | `0x002000cf` | `0x00200041` |
| `0x9a0338` | `0x003000ea` | `0x003000f1` |
| `0x9a0390` | `0x00c0052d` | `0x00c00528` |
| `0x9a0394` | `0x000028d9` | `0x0000394f` |
| `0x9a0300` | `0x00000003` | `0x00000003` (unchanged) |

Six of seven HBM timing registers moved to strap-5 values, but the geometry still resolved to
40960 MiB because the tier `0x77` was halved to 2048 MiB per FBPA across 20 live FBPAs. Strap-5
timings themselves would not load. The resulting state was informally called "the pg199 config"
in-channel. PG199 is NVIDIA's board code for the Drive A100, and there is an unreleased branch
of that name, but `0x22779000` is not a value any shipping or branch code writes, so the label
should not be read as naming a configuration the tooling implements.

Note also that **neither the shipping tool nor any unreleased branch re-executes DEVINIT, drives
the PMU, or touches FBFLCN.** A search of the full branch set for `devinit`, `PMU`, `FBFLCN` and
`0x101000` returns nothing. All DEVINIT work described here lives in analysis artifacts, not in
shipped code.

---

## Version inventory

### The seven-ROM comparison baseline

| Image | Version | Build date | Device | Subsystem |
|---|---|---|---|---|
| A100 PCIe 40 GB | `92.00.90.00.08` | 2022-01-05 | `0x20F1` | |
| A100 SXM4 40 GB | `92.00.45.00.03` | 2021-06-16 | `0x20B0` | `0x134F` |
| CMP 170HX 8 GB | `92.00.67.00.01` | 2021-05-14 | `0x20C2` | `0x1585` |
| CMP 170HX 10 GB | `92.00.66.00.02` | 2021-04-23 | `0x2082` | `0x1557` |
| CMP 170HX "16 GB" | `92.00.67.00.01` | same as 8 GB | `0x20C2` | `0x1585` |
| CMP 170HX 300 W | `92.00.6D.00.0A` | 2022-04-07 | `0x20C2` | `0x1585` |
| Drive A100 32 GB | `92.00.A0.00.01` | | `0x20BB` | |

### Revisions in the field on 8 GB cards

| Version | Date | Power limit | Memory clock field | Notes |
|---|---|---|---|---|
| `92.00.67.00.01` | 2021-05-14 | 250 W | 364 MHz | The stock production 8 GB image |
| `92.00.6D.00.09` | 2021-11-01 | 300 W | no memory OC | Exists but is not in the TechPowerUp collection; reported by a researcher holding the file, medium-high confidence |
| `92.00.6D.00.0A` | 2022-04-07 | 300 W | 432 MHz | The "mining" / OC image |

**VBIOS version makes no difference to whether the unlock works.** Four cards across two hosts,
two on each of `92.00.67.00.01` and `92.00.6D.00.0A`, showed identical unlock and Gen2 results:
`LnkCap 0x00456102`, `LnkCap2 0x00000006`, `LnkSta 0x1042`, `nvidia-smi` cur/max/width `2,2,4`,
identical Board PN `900-11001-0108-000`, GPU PN `20C2-105-A1`, subsystem `0x158510DE`, and the
same fuse triple `OPT=00000001/00000001/16680000`. Writing that "the 8 GB SKU carries
`92.00.6D.00.0A`" as a blanket statement is wrong; both versions are in the field.

### Memory clock: one clock, four multiples

The VBIOS memory field is **quarter-rate**. This resolves what was logged for two years as a
three-way conflict between 432, 729 and 1458 MHz.

| Relation | Multiplier | `92.00.67` (364 MHz field) | `92.00.6D.00.0A` (432 MHz field) |
|---|---|---|---|
| VBIOS field | ×1 | 364 MHz | 432 MHz |
| CUDA `deviceQuery` memory clock rate | ×2 | 729 MHz | |
| Marketing / spec MHz | ×4 | 1458 MHz | 1728 MHz |
| Gbps effective | ×8 ÷ 1000 | 2.9 Gbps | |

The 1728 MHz figure was confirmed via `nvidia-smi` on a card running `0A`.

> [!NOTE]
> **Open problem**
>
> Whether `1728 MHz` on the `0A` image is a valid strap or a boost point. Asked directly, the
> answer was an explicit guess: "I wanna say boost". Whether that VBIOS also changes voltage,
> power or core clock was asked and never answered.

### Public TechPowerUp images

Four CMP 170HX images exist publicly. **The "16 GB" and "0 GB" size labels are wrong and neither
unlocks memory.** TPU's "Memory Size" column could not be traced to any field in the `.rom` files
and is unreliable.

| TPU entry | Label | Actual | Device / subsystem |
|---|---|---|---|
| 257744 | 8 GB | The 8 GB production image | `10DE 20C2` / `10DE 1585` |
| 239457 | "16 GB" | Bit-for-bit identical to the normal 8 GB VBIOS apart from the `flash_status_ledger`, which changes on every flash including at the factory | `10DE 20C2` / `10DE 1585` |
| 268495 | "0 GB" | The 300 W `92.00.6D.00.0A` OC ROM | `10DE 20C2` / `10DE 1585` |
| 268984 | 10 GB | The 10 GB image | `10DE 2082` / `10DE 1557` |

TPU 268495 is identified as the 300 W ROM by a full field match: version `92.00.6D.00.0A`, build
2022-04-07, 1020 KB, device `0x10DE 0x20C2`, subsystem `10DE 1585`, MD5
`a58aae86e72b13d50603c15653350664`, SHA1 `efad37d514bb94ac345719a0c56d9cd147cddfb7`, UEFI not
supported, GPU clock 1140 MHz, boost 1410 MHz, memory clock 432 MHz, HBM2, memory size reported
as 0 MB, board power target 250.0 W, limit 300.0 W, adjustment range -60 % / +20 %.

A tester who flashed 239457 over 268495 reported memory ~300 MHz lower, the power limit dropped
to 250 W and no core offset available, consistent with moving from a 432 MHz field at 300 W to a
364 MHz field at 250 W, a 272 MHz effective drop.

> [!CAUTION]
> **TPU entry 283106 is not a CMP 170HX and must never be flashed to one**
>
> 283106 is an NVIDIA A100 / DRIVE-PG199-PROD image: version `92.00.A0.00.01`, build
> 2022-07-08, 976 KB, MD5 `ba22571080e412612964d130f0ce3880`, SHA1
> `ccac3c86cb901c5bb6758d3423d00383e6355c13`, device `0x10DE 0x20BB`, subsystem `10DE 14A1`,
> memory size 32751 MB, GPU clock 1260 MHz, boost 1260 MHz, memory clock 351 MHz, HBM2, no
> board power limit block. It has circulated as a "170HX reference". Flashing it via SPI
> programmer produced `NVRM: GPU 0000:0d:00.0: RmInitAdapter failed! (0x62:0x55:2674)` in
> dmesg, and the reported DevID stayed `10DE:20C2`. A follow-up attempt with `omgvflash` on a
> Windows laptop caused a BSOD.

> [!NOTE]
> **Open problem**
>
> Whether a genuinely distinct "16 GB" 170HX ROM exists. The comparison collection lists
> `cmp170hx_16gb_92.00.67.00.01.rom` as a separate file with the same version, build date,
> device ID and subsystem as the 8 GB image and the note "no cards ever shipped"; independently,
> TPU 239457 was found bit-for-bit identical to the 8 GB VBIOS. These may be the same file
> counted twice. An MD5 or SHA of the collection file against 239457 and 257744 would settle it.

### Per-SKU and cross-product ROM diffs

| Comparison | Total delta | Breakdown |
|---|---|---|
| 170HX 8 GB vs 10 GB | 2,684 B | NVGI `0x0000`-`0x5E00` 2,399 B (including four MAC blocks of ~384 B, about 1,533 B of MAC content); PciAt `0x5E00`-`0xC000` 36 B, all version and device ID; FwSec body `0xC700`-`0x47700` 249 B, training and config only |
| Drive A100 vs A100 PCIe 40 GB | 468,557 B (45 % of the ROM) | 96 KB larger signed range plus a completely different firmware build |
| Drive A100 GPU0 vs GPU1 | 49,852 B | 49,797 B (99.5 %) InfoROM, 55 B NVGI: same firmware, per-unit calibration only |

Only **two bytes differ in the NVGI bootstrap** between the 8 GB and 10 GB images: `0x0004` is
`0x52` versus `0x80` (header size/version field) and `0x000E` is `0x85` versus `0x57`, the
subsystem ID low byte encoding `0x1585` versus `0x1557`. Net of MAC content, the genuinely
functional SKU difference is tiny, which is consistent with the seven-byte restriction figure.

The published Drive A100 region breakdown (NVGI 155 B, PciAt 4,799 B, FwSec body 91,694 B,
unsigned tail 11,142 B, InfoROM 52,847 B) sums to 160,637 B, not 468,557 B. That is a real
inconsistency in the source analysis; the most likely explanation is that the region table covers
only overlapping windows while the total is a whole-file diff across images whose signed ranges
differ by 96 KB, shifting everything after them. Not reconciled by any source.

**FwSec body sizes differ between every GA100 product line**, which rules out FwSec/VN image
swapping structurally rather than merely as untested:

| Image | FwSec body | Span |
|---|---|---|
| 170HX 8 GB / 10 GB / "16 GB" | 241,664 B (baseline) | `0xC700`-`0x47700` |
| 170HX 300 W | 242,176 B (+512) | `0xC700`-`0x47900` |
| A100 SXM4 40 GB | 240,640 B (-1024) | `0xC700`-`0x47300` |
| A100 PCIe 40 GB | 244,224 B (+2560) | `0xC700`-`0x48100` |
| Drive A100 32 GB | **Unresolved**: the recorded body size (362,496 B) and the recorded span disagree; `0x5AC00 - 0xC700` = 320,768 B. Use the span, not the total, until a re-read settles it | `0xC700`-`0x5AC00` |

The VN preambles being identical across 170HX SKUs is the one thing that would have made a swap
plausible.

---

## What is and is not modifiable

Five targets, ranked by MAC-range membership.

| Target | Offset | Inside MAC? | Status |
|---|---|---|---|
| CFG1 strap-4 tier byte | `0x41D53` | Inside | **CLOSED.** Needs csecret(2). Proven by the 2026-05-08 byte-flip that stalled the Booter |
| PCIe Gen1 lock, 5 bytes / 3 DEVINIT sites | in `0x33800`-`0x41200` | Inside | **CLOSED.** Runtime Gen2 branches supersede it |
| ECB firmware blob | `0x14A00`-`0x33800` | Inside, and encrypted with csecret(6) | Contents unknown |
| Power limit 250 W to 300 W | `0x45E45` | Outside | **OPEN but untested.** CH341A only |
| `CTRL_OPT` fuse table | `0x47341` | Outside | Under investigation, semantics undetermined |

### The write path: verify-then-write binds payload to image

A controlled 2×2 experiment (VV-authenticated image × EWR payload) established the rule:

| VV'd image | EWR payload | Result |
|---|---|---|
| live | live | ERR = 0 |
| live | 8 GB | `0x9C` |
| 8 GB | 8 GB | ERR = 0 (success) |
| 8 GB | live | `0x9C` |

The fourth row is the clincher: the payload was the live flash content and was still rejected,
because VV had authenticated a different image. The rule is: authenticate a genuinely signed
image with VV, then write *that image's* bytes. It was proved end to end by writing 7,878 bytes
of foreign 8 GB content into the real VBIOS block, reading it back, and restoring it
byte-identically. **A genuinely signed 80 GB A100 VBIOS would therefore flash. Modified images
still die earlier, at `0x40` in VV.**

> [!NOTE]
> **Open problem**
>
> What is missing is a signed image that the 170HX's Board ID and fused device ID gates will
> then accept at boot; every cross-flash to date failed at that gate, not at the write. The
> cleanest next step is a VV+EWR of the *same-SKU* 300 W ROM onto a 250 W card, which is
> signed, same device ID and same board, to establish whether the boot-side gate is Board ID or
> something narrower.

---

## Failure signatures

Keep this table next to you before any flash attempt. See also
[troubleshooting](../procedures/troubleshooting.md).

| Signature | Meaning |
|---|---|
| `GFW_BOOT = 0x401` or `0x001` | Broken MAC. A byte inside the signed range changed |
| `GFW_BOOT = 0x8F`, PROM reads all `0xFF` | FWSEC HS-exit taint. FWSEC ran but GFW never proceeded past it, so the driver never reaches Booter |
| `kgspExtractVbiosFromRom_TU102: did not find valid ROM signature` then `RmInitAdapter failed! (0x62:0x25:2028)` | VBIOS state-register (SReg) data destroyed. **Reflashing a stock ROM does not help** |
| `kgspWaitForGfwBootOk_TU102: failed to wait for GFW boot complete: 0x65` | Seen during VBIOS-modification attempts on `92.00.66.00.02` |
| `RmInitAdapter failed! (0x62:0x55:2674)`, DevID unchanged | A foreign (Drive A100) image was flashed and did nothing functionally |
| `falcon halted` from `nvflash` | `nvflash` got past image validation with `--protectoff` and then failed running its own SPI-writer ucode |
| VV error `0x40` | A modified image, rejected in verify before the write stage |
| `0xBADF3000` | SPI not write-protected before power-on |
| Device Manager Code 10 (Windows) | Every locally patched 170HX VBIOS a tester produced gave this |

---

## Dead ends

Every entry was a real attempt with a real result. None should be retried without new
information. See [dead ends](../history/dead-ends.md) for the full project-wide list.

| Attempt | Result |
|---|---|
| Full A100 VBIOS cross-flash onto a 170HX | Card does not boot in secured mode and is unusable; memory size, SM count and shader count do not change; only the subsystem ID changes. Disproved 2024-07-17, reconfirmed 2026-07-19 and 2026-07-25 |
| A100 VBIOS onto a strap-modified 10 GB card | Bricks the card. Recovery required re-flashing the saved original ROM with an SPI programmer |
| Editing the strap byte `44` to `66` in the image and fixing the checksum | Driver fails to load. Consistent with the Falcon validating at power-up and dropping the chip into non-secure mode. Superseded by the runtime CFG1 write at `0x009a0204` |
| Single byte flip inside the signed range (`0x41D53`) | Booter stalls, `GFW_BOOT=0x001` |
| Simple ROM splicing, A100 sections into a 170HX image | Fails twice over: strap-table offsets differ per ROM and each section is independently MAC'd |
| FwSec / VN image swap between SKUs | Ruled out structurally by the body-size mismatch |
| A30 FWSEC module transplant | Dead on arrival: the signed code modules are already **identical** between the 10 GB 170HX and the A30, so the module gains nothing. The differentiating data is non-code configuration inside the verified section |
| `nvflash` with patched image validation plus `--protectoff` | Gets further, then `falcon halted` when nvflash runs its ucode, which is the SPI writer itself. `omgvflash` and `nvflashk` likewise refuse an edited BIOS |
| Writing the SPI controller registers from software | See below. Closed hard |
| NVGI as an attack surface | Closed by boot ordering: DEVINIT overwrites NVGI's MR1/MR2/MR3 writes, and FWSEC re-raises any PLM NVGI lowers |
| TOCTOU on the VBIOS | Wiped the SReg data; card fails with no valid ROM signature and reflashing stock does not recover it |
| 8 GB VBIOS onto a 10 GB card | Flashed and reverted successfully with a patched nvflash, but the 8 GB image does not boot on the 10 GB card, and strap edits fail an image check during flashing. Caveat: no reboot between flashes, so this is suggestive rather than definitive |
| Maxwell-era ECC unlock ported to Ampere | Never demonstrated on GA100; caveated by its own author as non-trivial for Ampere |
| The sim/emu HBM2e ROM as a template | Sim ROMs are ~230 KB with a completely different layout, and even there only the primary strap table was raised `66` to `77` while the copy at `0x1AD72` still reads `00 90 66 02` |
| Modifying an already-decrypted VBIOS | Undervolting and memory-timing locations were identified, but **every modification attempted resulted in a failed driver load**. Patching the driver to accept the modified state was never tried |
| Self-signing a custom VBIOS | Reported to have been briefly possible during a leak window. No usable signing capability exists now. Treat the leak-window detail as anecdote |
| VBIOS modification as a route around the GSP-RM problem | "Checksum failed". Defeating the Booter chip-ID gate by VBIOS flash "didn't work at all" |
| Believing the TechPowerUp "Memory Size" column | It maps to no field in the `.rom` files |

### The SPI controller cannot be written from software

Documented explicitly so it is not retried. The refire-chain HS exploit **did** successfully open
the SPI PLM at `0xD7D8`, setting it to `0x00000000`, confirmed open with rp=0 wp=0, which proves
the exploit reaches and modifies the PLM from HS mode. Despite the PLM reading fully open:

| Register | Write | Readback |
|---|---|---|
| `SPI_DATA` `0xE4A0` | `0xDEADBEEF` from PL0 | `0x00000000` |
| `SPI_CTRL` `0xE5A0` | `0xDEADBEEF` from PL0 | `0x00000000` |
| `ROM_SERIAL_BYPASS` `0xE204` | `0xDEADBEEF` from PL0 | `0x00000000` |
| `0xE4A0` / `0xE5A0` | direct HS-ROP writes | report "~" (not landed), registers stay `0x0` |

Conclusion: a hardware write filter enforced by the secure boot state machine drops all writes to
the SPI controller from any agent except the GFW boot firmware (SEC2/PMU during boot). **The CFG1
flash byte cannot be written by any software path on this card.**

---

## Open questions specific to the VBIOS

Ranked most tractable first. The cross-cutting list is on
[open questions](../frontier/open-questions.md).

1. **Flash the 250 W to 300 W power limit at `0x45E45`.** The three-byte field reads `90 D0 03`
   and should become `E0 93 04`. It sits 9,285 bytes into the 15,616-byte unsigned tail
   (`0x43A00`-`0x47700`) so it cannot break
   the MAC, the same class of change as the `0xFF`-padding test that already booted. Blocked only
   because `nvflash` is refused even for unsigned-tail changes, so it needs a CH341A, cooler
   removal and repaste. Open and untested since 2026-05-09.
2. **Determine `NV_FUSE_CTRL_OPT_*` semantics.** The 25-entry table at `0x47341` reads all-zero
   across 13 probed GA100 cards. Also in play: `PBUS_SW_SCRATCH(1)` at `0x001404` reads
   `0x20042000` with bit 14 clear, and bit 14 is *believed*, never write-tested, to make firmware
   skip its CTRL_OPT-zeroing loop. Inert on cards already at their fuse floor.
3. **Inject a HULK cert at `0xFE504`** (see above).
4. **Recover csecret(2)**, which would open every in-MAC edit at once, all seven restriction
   bytes. The offline oracle removes the need for flash cycles during a DFA campaign. Very high
   effort.
5. **Do unsigned-tail memory edits take effect?** The `freqDelta` experiment described above.
6. **Decrypt the production Falcon/DEVINIT code** via the debug-IMEM recipe.
7. **The A30 alignment lead.** An A30 VBIOS `92.00.66.00.0x` is reported to be almost identical
   to the 10 GB 170HX's `92.00.66.00.0x`, on the reasoning that the A30 is an A100 with three
   HBM2 stacks in operation and stack count is fuse-controlled. Complication: the signed code
   modules are already identical, so the only value is in the non-code configuration data inside
   the covered region, which is exactly the part that needs csecret(2). Diffing an A30 ROM
   against the 10 GB 170HX ROM would enumerate that configuration delta.
8. **Diff software versus hardware SPI traffic.** The unverified third-hand claim is that
   `nvflash`/`omgvflash` write "in-between registers" a bare SPI programmer does not touch. A
   logic analyzer on the SPI bus during both a software and a hardware flash would be cheap and
   decisive.

> [!NOTE]
> **Open problem**
>
> Whether the strap table is MAC-verified *in practice*. One position holds that even if
> `0x41D53` is inside the declared range, the Falcon may not actually check it. The counter is
> the 2026-05-08 byte-flip test at that exact offset, which stalled the Booter. Weight strongly
> favours "it is verified". The complication is that the *observed* in-channel failure
> ("can't modify the straps or image check fails") is a **host-side nvflash check**, not a
> boot-time Falcon check, so the two positions are partly talking past each other. A CH341A
> flash of a strap-edited image, bypassing nvflash entirely, plus a `GFW_BOOT` read would
> settle it. Nobody has reported doing this.

> [!NOTE]
> **Open problem**
>
> Fuses versus VBIOS as the residence of the 170HX limits. The engineering-sample A/B flash
> shows the VBIOS carries the memory cap, the PCIe cap and *part* of the compute penalty, but
> not all of it: cross-flashing a 170HX VBIOS onto an engineering-sample GA100 that skips
> signature checking imposed only **1/12 FP64 and 1/8 FP32**, versus **1/64 and 1/32** on a real
> 170HX, a residual factor of roughly 5 on FP64 and 4 on FP32 that must come from elsewhere. The shipping unlock recovers full
> SM throughput by writing SS0/SS1 at runtime, which strongly suggests the remainder was the
> `0x00823804`-gated feature override, but the engineering-sample experiment has never been
> re-run with SS0/SS1 also written. That the shipping unlock is pure software does not settle
> the question: it overrides state at runtime rather than proving where the default came from.

> [!NOTE]
> **Open problem**
>
> Batch-level VBIOS variation from suppliers. A single commercially interested source
> identifying as a technical employee of a bulk holder stated "we have two kinds of VBIOS for
> 170hx here, one has higher bandwidth". No version strings and no bandwidth figures were given.
> It is at least consistent with both `92.00.67.00.01` (364 MHz field) and `92.00.6D.00.0A`
> (432 MHz field) being in the field. Unresolvable from the record.

---

## Related pages

- [Board and variants](board-and-variants.md): device IDs, board part numbers, die markings
- [Memory subsystem](memory-subsystem.md) and [memory geometry](../unlock/memory-geometry.md):
  what CFG1 and LMR actually do
- [Fuses and OTP](fuses-and-otp.md): the layer the VBIOS cannot reach
- [Falcon and Booter](../unlock/falcon-and-booter.md): the mechanism that replaced VBIOS modding
- [PCIe subsystem](pcie-subsystem.md) and [PCIe Gen2](../unlock/pcie-gen2.md)
- [Recovery](../procedures/recovery.md): what to do when a flash goes wrong
- [Register index](../appendix/register-index.md)
