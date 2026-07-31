# The SEC2 Falcon and the Booter Load microcode

**What this page covers.** The security coprocessor that the whole CMP 170HX unlock runs on: what
the SEC2 Falcon is, what the "Booter Load" microcode does, how heavy-secure mode is entered and
left, the internal layout of the booter image in both of its address spaces, where the GSP
signature buffer sits, and exactly how the patched driver invokes the booter. The exploit itself
lives on [The ROP chain](rop-chain.md); the masks it opens live on
[Privilege Level Masks](privilege-level-masks.md).

**The key result in two sentences.** NVIDIA's own signed, AES-encrypted `booter_load` microcode is
loaded and authenticated normally, and is then corrupted *after* authentication has already
succeeded, by a signature buffer the host driver controls. No signature is forged, no key is
extracted, and no attacker-supplied instruction is ever executed: the booter becomes the unlock's
execution engine while remaining, byte for byte, the microcode NVIDIA shipped.

---

## 1. Why a Booter exists at all

The GA100 die carries two very different processors relevant here.

| Processor | Location | Core | Crypto | Role |
|---|---|---|---|---|
| SEC2 Falcon | BAR0 `0x00840000` | Falcon v4/v5, 16-bit Harvard | AES + RSA + SCP secrets | Security coprocessor. Can decrypt and validate its own code image. |
| GSP | BAR0 `0x00110000` / `0x00111000` | NVIDIA RISC-V (NVRISCV) | none | Runs GSP-RM, the resource manager firmware. |

Because the GSP RISC-V core has no crypto functionality, it cannot validate its own image.
Validation is delegated to a SEC2 Falcon microcode called the *booter*. Two booters exist,
`booter_load` and `booter_unload`; this page is about `booter_load`.

The booter is **not** part of the [VBIOS](../hardware/vbios.md). It ships inside the driver package
as a compiled-in BINDATA array in `nvidia.ko`, and it is version-specific, as is the encrypted GSP
firmware it validates. In driver 610 the GA100 array is:

```text
kgspBinArchiveBooterLoadUcode_GA100_BINDATA_LABEL_IMAGE_DBG_data[]
  in src/nvidia/generated/g_bindata_kgspGetBinArchiveBooterLoadUcode_GA100.c
  DATA SIZE (bytes): 60160
  COMPRESSED SIZE (bytes): 34145
```

Consequently no separate booter file is needed to run the exploit. The driver already carries it.

The boot chain the unlock attacks, end to end, is: VBIOS loaded from SPI flash at power-up, an
on-die Falcon validates the VBIOS, the chip enters secure mode, the driver supplies
`gsp_tu10x.bin` whose signature the Falcon checks, and the driver then uses the GSP client to read
memory capacity and expose the device. The unlock attacks the fourth step, by planting a payload in
the GSP signature buffer the booter DMAs.

---

## 2. The Falcon security model

Falcon has had three execution modes since Maxwell.

| Mode | How entered | What it can do |
|---|---|---|
| Non-Secure (NS) | Load any code, set BOOTVEC, STARTCPU | The only mode reachable without NVIDIA-signed microcode. Restricted from many registers and from DMA. |
| Light Secure (LS) | Only from a Heavy-Secure context (GM20x onward) | Between NS and HS. |
| Heavy Secure (HS) | Hardware grants it after a successful MAC comparison when the PC lands on a code block tagged secure | The Falcon becomes a black box: internal state cannot be read or written from outside. Runs at LEVEL2/L3 and can rewrite privilege-level masks and program protected regions. |

The project's "L0 to L3" privilege-level vocabulary refers to the same model. See
[Privilege Level Masks](privilege-level-masks.md) for how those levels are enforced per register.

`booter_load` can never be executed in NS mode. Its body is AES-encrypted and is only decryptable
inside the Falcon in HS mode. The Falcon enters HS by running the 0x100-byte cleartext NS preamble
and then issuing the special instruction that decrypts the code, verifies it and switches to HS.
The consequence is architectural and is the reason the whole unlock is shaped the way it is:

> [!NOTE]
> **The rule that shapes everything**
>
> Every HS-privileged register write in the unlock must be issued from inside the hijacked
> genuine booter. A home-grown microcode cannot do it, because a home-grown microcode cannot be
> made to run in HS.

The HS entry routine, as reverse-engineered for Tegra TSEC and structurally the same on GA100 SEC2,
computes `microcode_start = (*SEC & 0xFF) << 8` and `microcode_size = ((*SEC >> 24) & 0xFF) << 8`,
calculates a Davies-Meyer MAC of the microcode into `$c5`, then runs:

```asm
csecret $c3, 0x1
ckeyreg $c3
cenc     $c3, $c7
ckeyreg  $c3
cenc     $c4, $c5
csigcmp  $c4, $c6
```

A zero start or size raises `OP_SECURE_FAULT`. Four conditions must hold to authenticate: the
microcode pages must be mapped at a pre-chosen virtual address, marked secret, that information
loaded into the `SEC` register, and a valid MAC present in crypto register 6.

> [!WARNING]
> **Two different verification schemes, do not conflate them**
>
> The immutable boot ROM's check of the HS booter image is described in the corpus as an RSA-3K
> check, and a 384-byte signature blob does ship alongside the image at `PATCH_LOC = 0x8900`.
> Separately, the booter's *own* verification of the GSP image it loads was traced to
> `_acrVerifySignature_TU10X` to `_acrCalculateDmhash_TU10X` to
> `_acrDeriveLsVerifKeyAndEncryptDmHash_TU10X` to `_acrMemcmp`, which is a Davies-Meyer hash plus
> an AES key derivation keyed from a `csecret`, with no RSA on that path. The booter does contain
> a separate PKA/modexp block (`rsa_pubkey_load 0x4768`, `pka_modexp_run 0x54ab`) used elsewhere.
> Confidence in the reconciliation is medium: nobody in the archive stated it in exactly these
> terms.

Neither scheme is broken by the unlock.

---

## 3. Harvard architecture: two address spaces that must never be mixed

> [!CAUTION]
> **IMEM addresses and DMEM addresses look identical and are not interchangeable**
>
> The SEC2 Falcon is a **Harvard-architecture** core with separate 16-bit instruction memory
> (IMEM) and 16-bit data memory (DMEM) spaces. `0x6340` as an IMEM address is meaningless code;
> `0x6340` as a DMEM address is the stack-canary guard global. Several circulating documents mix
> the two into a single "memory map" and are wrong. Every address on this wiki is labelled IMEM,
> DMEM, CSB (Falcon I/O) or BAR0.

| Property | IMEM | DMEM |
|---|---|---|
| Size | `0x10000` (64 KB) | `0x10000` (64 KB) |
| Falcon virtual window | `0x4000000`-`0x400FFFF` | `0x4010000`-`0x401FFFF` |
| Block alignment | 256 bytes (`FLCN_BLK_ALIGNMENT`) | 256 bytes |
| What the exploit touches | nothing | `0x0800`-`0xFFFF` |

Because the GSP signature buffer lives in DMEM, the signature DMA can smash DMEM only and can never
write IMEM. That single fact is why the exploit is pure return-oriented programming over an
already-signed image rather than code injection. It also means DMEM's 16-bit space cannot itself
address a 32-bit BAR0 register, so the payload needs a gadget that drives the Falcon's BAR0 master.

Two further spaces appear throughout:

- **CSB / Falcon I/O**, addressed by `iord` / `iowrs I[...]`. Examples: `I[0x1000]` is MAILBOX0,
  `I[0x9100]` is `FALCON_CSBERRSTAT`, `I[0x1c000]`/`I[0x1c100]`/`I[0x1c200]` are the BAR0 master.
- **BAR0 / PRI**, the host's 32-bit view of the privileged register interface. Host, SEC2 and the
  GSP RISC-V all talk over PRI; PLMs gate regions of it.

---

## 4. SEC2 as seen from the host: BAR0 register map

SEC2 sits at `NV_PSEC_BASE = 0x00840000` and is a Falcon core, not RISC-V (`HWCFG2` bit 10 reads
0). Full offsets, verified by a working driverless C loader on GPU `10de:20c2`:

| Register | Offset | Absolute | Notes |
|---|---|---|---|
| `IRQSCLR` | `+0x004` | `0x00840004` | |
| `IRQSTAT` | `+0x008` | `0x00840008` | |
| `MAILBOX0` | `+0x040` | `0x00840040` | Host alias of Falcon CSB `I[0x1000]` |
| `MAILBOX1` | `+0x044` | `0x00840044` | |
| `SFTRESET` | `+0x07c` | `0x0084007c` | PL0 write does nothing to HSMODE |
| `FALCON_RM` | `+0x084` | `0x00840084` | |
| `EXCI` | `+0x0d0` | `0x008400d0` | Exception info |
| `HWCFG2` | `+0x0f4` | `0x008400f4` | bit 10 = RISCV |
| `CPUCTL` | `+0x100` | `0x00840100` | bit1 STARTCPU, bit3 IREADY, bit4 HALTED, bit5 STOPPED, bit6 ALIAS_EN |
| `BOOTVEC` | `+0x104` | `0x00840104` | |
| `DMACTL` | `+0x10c` | `0x0084010c` | bit1 DMEM_SCRUB_PENDING, bit2 IMEM_SCRUB_PENDING |
| `DMATRFBASE` | `+0x110` | `0x00840110` | `(phys >> 8) & 0xFFFFFFFF` |
| `DMATRFMOFFS` | `+0x114` | `0x00840114` | |
| `DMATRFCMD` | `+0x118` | `0x00840118` | bit0 FULL, bit1 IDLE, bits2-3 SEC, bit4 IMEM, bit5 WRITE, bits8-10 SIZE (`0x6` = 256 B), bits12-14 CTXDMA, bit16 SET_DMTAG |
| `DMATRFFBOFFS` | `+0x11c` | `0x0084011c` | |
| `DMATRFBASE1` | `+0x128` | `0x00840128` | `((phys >> 8) >> 32) & 0x1FF` |
| `CPUCTL_ALIAS` | `+0x130` | `0x00840130` | |
| `TRACEPC` | `+0x14c` | `0x0084014c` | bits [23:0] = PC snapshot |
| `IMEMC0` | `+0x180` | `0x00840180` | bit24 AINCW, **bit28 SECURE**, bits23:8 BLK, bits7:2 OFFS |
| `IMEMD0` | `+0x184` | `0x00840184` | |
| `IMEMT0` | `+0x188` | `0x00840188` | |
| `DMEMC0` | `+0x1c0` | `0x008401c0` | |
| `DMEMD0` | `+0x1c4` | `0x008401c4` | |
| `SCTL` | `+0x240` | `0x00840240` | bit0 LSMODE, bit1 HSMODE (read-only), bit14 AUTH_EN |
| `IMEM_PRIV_LEVEL_MASK` | `+0x280` | `0x00840280` | |
| `DMEM_PRIV_LEVEL_MASK` | `+0x284` | `0x00840284` | reads `0xFF` fully open in LS mode |
| `FBIF_TRANSCFG(n)` | `+0x600 + 4n` | `0x00840600`+ | TARGET bits [1:0]: 0 LOCAL_FB, 1 COHERENT_SYSMEM, 2 NONCOHERENT_SYSMEM; MEM_TYPE bit 2 = PHYSICAL |
| `FBIF_CTL` | `+0x624` | `0x00840624` | bit 7 = ALLOW_PHYS_NO_CTX |
| `FALCON_ENGINE` | `+0x3c0` | `0x008403c0` | bit0: 1 = reset, 0 = run |
| `RESET_PRIV_LEVEL_MASK` | `+0x3c4` | `0x008403c4` | The reset PLM. See section 9. |
| `PRIVSTATE_PLM` | `+0x3d0` | `0x008403d0` | Named only, never write-tested |
| `SCP_CTL_P2PRX` | `+0x530` | `0x00840530` | bit3 SFK_LOADED |
| `KFUSE_LOAD_CTL` | `+0x11ec` | `0x008411ec` | read to trigger SFK load |

The GSP side, for contrast: `NV_FALCON2_GSP_BASE = 0x00111000`, `RISCV_STATUS 0x00111240`,
`RISCV_CPUCTL 0x00111268`, GSP `MAILBOX0 0x00110040`, GSP FBIF base `0x00110600`.

`EXCI` decodes as `expc = ((exci >> 28) << 20) | (exci & 0xFFFFF)` and
`excause = (exci >> 20) & 0x1F`, with causes `0x08` ILL_INS, `0x09` INV_INS, `0x0a` MISS_INS,
`0x0b` DHIT_INS (IMEM block present but not BROM-authenticated), `0x0d` SP_OVERFLOW, `0x0f`
BRKPT_INS, `0x10` DMEM_MISS, `0x11` DMEM_DHIT, `0x12` DMEM_PAFAULT, `0x13` DMEM_PERM, `0x15`
BROM_CALL, `0x16` KMEM_VIOLATION, `0x17` BMEM_PERM.

---

## 5. The Booter Load image

### 5.1 File layout

| Region | Offsets | Contents |
|---|---|---|
| NS bootstrap | `0x0000`-`0x0100` | Cleartext. 256 bytes. |
| HS code | `0x0100`-`0x8600` or `0x0100`-`0x8700`; **the sources disagree by 256 bytes** | AES-128-ECB encrypted. |
| Data (`osData`) | `0x8700` onward on the arithmetic; `0x8600` is also quoted | §11's `hsSigDmemAddr = patchLoc - dataOffset` derivation requires `0x8700` (`0x8900 - 0x8700` = DMEM `0x200`), and so does the 34,304-byte secure-code measurement (`0x0100`-`0x8700` is 34,304 bytes; `0x0100`-`0x8600` is only 34,048). Both lines of evidence point the same way, so `0x8600` is the weaker reading. Verify against your own image before aligning a decryption offset. |
| Signature | `0x8900` (`PATCH_LOC`) | 384 bytes |

Uncompressed code size is `0x8700` = 34,560 bytes. Measured section sizes for the analysed
debug-signed build are 34,304 bytes of secure code, 25,600 bytes of data and 256 bytes of
non-secure code. Raw-extracted GA100 files are zero-padded out to 60,100 bytes; the compiled-in
BINDATA blob is 60,160 bytes.

The encrypted region starts exactly at `0x100`, a multiple of 16, and the first decrypted
instruction there is:

```text
89 fc ff 00    mov $r9 0xfffc
```

### 5.2 The crypto break

The finding that made a plaintext disassembly possible without any leaked source:

> [!NOTE]
> **The debug and production booter images contain exactly the same cleartext code**
>
> Only the AES key differs. The debug image is encrypted with a non-secret numbered test key, so
> the production HS code can be read by decrypting the debug image. The underlying cryptography
> discovery was made in May 2026; it was applied to GA100 on 2026-07-01.

Practical markers:

| Quantity | Value |
|---|---|
| Debug key number | 37 |
| AES-128-ECB ciphertext of the trailing zero padding under that key | `717D1494 EACA317F F1061952 58B38377` |
| Disassembler | `envytools` / `envydis` |

If the 16-byte constant above appears just before the file's own zero region, the debug blob was
extracted correctly and is correctly aligned; if it decrypts back to zeroes with the test-key tool,
the decryption is right. Production blobs show a different trailing pattern. One workflow detail
that costs hours if missed: the 4-byte round keys must be fed to the AES/Rijndael tool in the
**reverse** order from how they appear in human-readable form, because the key number sits in the
last round key rather than the first (confidence: medium, single actionable instruction, but the
workflow it describes demonstrably produced correct output).

### 5.3 Extraction

Extraction was done by patching NVIDIA's own `extract-firmware-nouveau.py` to emit only GA100 prod
and debug booters, parsing
`kgspBinArchiveBooter{Load,Unload}Ucode_GA100_BINDATA_LABEL_IMAGE_{PROD,DBG}_data` and the matching
`..._SIG_{PROD,DBG}_data`. The **GA100 signature size is 384 bytes per signature**, where TU10x uses
16, so the calls are `booter('ga100','load',384,'prod')` and the three siblings. All non-GA100 chips
(tu102, tu116, ga102, ad102, gh100, gb100, gb202) were commented out of `main()`.

A second variant, `extract-firmware-nouveau-ga100-raw.py`, strips all container structure
(`nvfw_bin_hdr` with its `0x10de` magic and 6 dwords, `nvfw_hs_header_v2` with 9 dwords, the
signature blob, `patch_loc` / `patch_sig` / `fuse_ver` / `engine_id` / `ucode_id` / `num_sigs`, and
the descriptor) and writes only the raw firmware to `booter_{load,unload}_{prod,dbg}-<ver>_raw.bin`.
That raw layout feeds envydis and objdump and is the input to all later tooling.

A second extraction route works from a loaded stock driver: read SEC2 IMEM through `IMEMC 0x840180`
with bit 25 set for auto-increment and `IMEMD 0x840184` for offsets `0`..`0x8700`, read DMEM through
`DMEMC 0x8401c0` / `DMEMD 0x8401c4`, then concatenate IMEM(NS+HS) + DMEM.

Booter geometry can also be recovered **without a disassembler** by scanning the first `0x100` bytes
of the raw image: `imm_before(ns, ff9f04)` yields the NS end and
`imm_before(ns, fd9e04bb9002b69410)` yields the DMEM offset, where `imm_before` requires the byte
four positions before the marker to be `0x89` (the `mov $r9 imm24` opcode) and then assembles the
little-endian 24-bit immediate. If either marker is missing, or `dmem <= base`, the parser raises
"not an ACR booter image". Loading then writes `img[0:ns]` to IMEM 0 unsecured, `img[ns:dmem]` to
`IMEM[ns]` with the SECURE bit `1 << 28` set, and `img[dmem:]` to DMEM 0.

### 5.4 Version portability

| Driver branch | GA100 `booter_load` | Gadget addresses valid |
|---|---|---|
| 515-era | Different build; canary global at `0x2B20` or `0x2D20` | No |
| 580 through 610 | **Bit-identical** (verified across 580.173.02, 580.159.04, 580.159.03, 610.43.02, 595.84) | Yes |

Every ROP gadget address on this wiki therefore holds across the entire 580-610 range without
re-derivation. The 515 booter is the one that was publicly disassembled before this project, and it
does not carry the vulnerability.

The published paper's cross-version corpus spans branches 450, 460, 470, 510 (two point releases),
515, 525, 535, 560, 570 and 580. The 510 SEC2 booter's signature path uses only constant or clamped
DMA lengths with no metadata-sized copy; the 580 booter exhibits the unbounded copy; the 525 image
could not be recovered because booter packaging changed.

> [!NOTE]
> **Open problem: first affected driver branch**
>
> The overflow is **absent in 510** and **present in 580**. Branches 515 through 570 are
> **indeterminate**. Settled by recovering and analysing the 515, 535, 560 and 570 GA100 booters
> for the metadata-sized copy.

### 5.5 Lineage naming

GA100 uses **Turing-generation** firmware: the GSP blob is `gsp_tu10x.bin` and the SEC2 booter is
Turing-lineage `booter_load`. This is stated in NVIDIA's own tree at
`nouveau/extract-firmware-nouveau.txt`, and is corroborated by the TU102-suffixed RM symbols on the
failure path (`kgspBootstrap_TU102`, `s_executeBooterUcode_TU102`). The correct naming, after an
in-channel correction:

| Prefix | Covers |
|---|---|
| `tu10x` | All Turing |
| `ga100` | A100 and CMP 170HX only |
| `ga10x` | Other Ampere (GA102, RTX 3090, CMP 90HX) |

Because the 170HX loads the Turing `booter_load`, it inherits the Turing booter's DMA/signature
overflow. Whether cards that load the Ampere booter inherit it from that path is contested and
unresolved; see [Open questions](../frontier/open-questions.md).

---

## 6. Booter internals: the IMEM function map

All addresses in this table are **IMEM** (code) addresses in the decrypted debug-signed image
`booter_load_ga100_dbg_seccode.fuc5.asm`. The annotated listing
`booter_load_ga100_dbg_seccode.annotated.fuc5_v2.asm` contains 10,934 unmodified code lines with
per-function banners.

| IMEM | Symbol | Role |
|---|---|---|
| `0x0100` | `_start` | Entry point. Ten-phase HS prologue. |
| `0x04a7` | (self-loop) | `3e a7 04 00 B lbra 0x4a7`. The payload fill dword's spin-park. |
| `0x04d0` | `_start` exit | |
| `0x04d4` | `dma_copy_block` | The real DMA-to-DMEM cycle (`xdld`). **The overflowing frame.** |
| `0x0602` | `dma_dispatch_descriptors` | Submits up to four sub-descriptors, tags `r14 = 0xa0..0xa3` |
| `0x0c7c` | `regblock_read_guarded` | |
| `0x0cbd` | elevator | `mov $r10 $r0` inside `0x0c7c` |
| `0x0ccb` | `regtable_rw_indexed` | Indexed access to register descriptor tables; ends `mpopaddret $r5 0x8` |
| `0x0d66` | ACR mutex acquire | Error `0x1a` if the id byte reads 0 or `0xff`, `0x1c` on bad type |
| `0x0e85` | `memcpy` | |
| `0x0aa1` | `tgt_falcon_bringup` | Brings up the target Falcon; errors `0x1c`, `0x11` |
| `0x1034` | `watchdog_set` | Seeds `I[0x1c300]` with `0x1312d00` (20,000,000) |
| `0x1064` | `mailbox_wait_ready` | Polls `I[0x1c000]` bits [14:12]: 0 done, 1 spin, else error `0x15` |
| `0x10aa` | `reg_write_indirect` / `_acrlibBar0RegWrite_TU10X` | **The arbitrary BAR0 write primitive.** ~70 call sites. |
| `0x10b9` | (mid-entry) | Skips the `r10`/`r11` to `r0`/`r1` marshalling |
| `0x10ff` | `mpopaddret $r3 0x4` | `0x10aa`'s epilogue; makes the write self-chain |
| `0x1196` | `reg_read_indirect` | |
| `0x14cf` | `tlb_scan_invalidate` | Flushes stale mappings of the image itself, range `[0, 0x8700)` |
| `0x154a` | `wpr_desc_validate` | Magic `0x371a60b3` at +0, `0xdc3aae21` at +4; errors `0x89`-`0x90` |
| `0x19a2` | `va_to_pa_walk` | Three-level software page walk; error `0x2` |
| `0x1b44` | `set_1180f8_bit24` | ORs `0x01000000` into `0x001180f8` |
| `0x1ba3` | `check_1180f8_2724` | Requires `0x001180f8[27:24] == 0`, else error `0x88` |
| `0x1c0e` | `set_1180f8_top_nibble` (finalize) | Clears [31:28] and ORs `(r0 << 28)`; epilogue `0x1c72` |
| `0x1c75` | `check_1180f8_nibbles` | Requires [31:28] == 0 **and** [23:20] == 0, else error `0x29` |
| `0x1d0f` | `report_status` | Writes `$r0` to MAILBOX0 |
| `0x1d3b` | `f100_field_save_restore` | RMW of register `0xf100` bits [4:6] through DMEM `0x1900` |
| `0x1e09` | `scp_key_derive` | `csecret $c7` with HW secret `0x37` or `0x36` |
| `0x1f92` | `read_820344_820348` | |
| `0x1fb9` / `0x1fbd` / `0x1fca` | elevators | See [ROP chain](rop-chain.md) |
| `0x21f4` | `image_dma_loader` | Call site `0x2725` |
| `0x2120` | `chunked_dma_copy` | `0x100`-byte chunks against register `0x4b00` |
| `0x22ba` | `booter_load_wpr_main` | Errors `0x5`, `0x89`, `0x8a`, `0x96`, `0x98`, `0x9c`, `0xa4` |
| `0x27fa` | rejoin point inside `0x22ba` | Writes `D[0x6f8]`/`D[0x6fc]`/`D[0x648]`; touches **no** WPR2 register |
| `0x28ac` | `wpr_region_check` | Error `0x5` |
| `0x291e` | `wpr_region_program` | Actually writes `0x001fa824`/`0x001fa828`; rejects empty regions |
| `0x2e80` | `image_auth_decrypt` | Streams `0x100`-byte chunks, key handle `0x17d78414` |
| `0x3747` | `image_copy_verify` | Normal return `0x2740` |
| `0x37b3` | signature DMA call site | `lcall 0x4d4` |
| `0x37b7` | post-DMA result check | `ld $r9 D[$r1+0x50]` |
| `0x399a` | `ls_sig_verify` | Requires `r10 == 0x700`; error `0x98` |
| `0x3c8f` | `firmware_load_main` | Magic `'FREE'` / `'HEAP'` at DMEM `0x5f00` |
| `0x4768` | `rsa_pubkey_load` | Modulus zero-padded to `0x200`, `e = 0x10001` |
| `0x54ab` | `pka_modexp_run` | Errors `0x63`-`0x6d` (`0x6c` timeout) |
| `0x59c4` | `antirollback_version` | Key handle `0x17d78400`; errors `0x5c`, `0x1` |
| `0x683f` | `boot_mode_dispatch` | |
| `0x68ed` | `reg_init` | Writes `0x110624 = 0x90`, `0x110684 = 1`, `0x11126c = 1` |
| `0x6a71` | `chipid_gate` | Accepts chip IDs `0x170` and `0x171` only; error `0x4b` |
| `0x6abd` | `rsa4096_pubkey_load` | Four 512-byte tables |
| `0x76ee` | `fb_size_compute` | Decodes LMR. See [memory geometry](memory-geometry.md). |
| `0x79cc` | `memcfg_program` | |
| `0x7a64` | `memcfg_apply_poll` | Timeout 100000, error `0xa6` |
| `0x7c65` | `memcfg_timing_program` | Timeout 125000, error `0xa7`, base constant `0x32a` |
| `0x7dd9` | `__stack_chk_fail` / `panic()` | Writes `0x47` to MAILBOX0, spins at `0x7def` |
| `0x7de9` | (panic body) | Prints whatever is in `$r15`. Basis of every debug ROP. |
| `0x7df3` | `memcmp_ct` | Constant-time compare |
| `0x7e76` | `secure_teardown` | Never returns |
| `0x7eef` | crypto self-zero sweep | Inside `secure_teardown` |
| `0x7f2f` | exit gadget inside `secure_teardown` | The shipping payload's terminator |
| `0x7f82` | **`main`** | |
| `0x8137` | `booter_load_wrap` | |
| `0x815a` | canary-check tail / stack eater of `booter_load_wrap` | See note below |
| `0x8224` | `csb_write` | Store is `iowrs I[$r10] $r11` at `0x8232` |
| `0x8262` | bare `ret` | Useful alignment gadget |
| `0x8264` | `csb_read` | |
| `0x8307` | `fbif_set_bit800` | Sets bit `0x800` in `0x001fa814`/`0x001fa818` under mask `0x0ffff8ff` |

> [!NOTE]
> **Resolved: `0x815a` is inside `booter_load_wrap`**
>
> One catalogue called it "the main canary-check tail"; another annotated it as "a stack-eater in
> `booter_load_wrap` that checks the canary and does nothing". The annotated v2 listing settles
> it. `main` runs `0x7f82` to `0x8134`, where its own canary check ends in `mpopaddret $r0 0x10`.
> `booter_load_wrap` runs `0x8137` to `0x8173`, ending in `mpopaddret $r0 0x4`, and the next
> function banner is `nibble_rmw` at `0x8176`. `0x815a` therefore lies inside `booter_load_wrap`,
> reached by the `bra b32 $r10 0x0 e 0x815a` at `0x8150` that skips the `boot_mode_dispatch
> (0x683f)` call. It is that wrapper's canary-check tail; `main`'s own tail is the separate block
> at `0x811d`. The second catalogue was right.

---

## 7. The boot flow

### 7.1 `_start` (IMEM `0x0100`): the ten-phase HS prologue

1. Scrub the SCP state (`csigclr` / `csecret` / `cxor`) at `0x0107`. Each `csecret $cN 0x0` is
   immediately followed by `cxor $cN $cN`, so the bank is zeroed the moment it is provisioned.
2. Clear every general-purpose register `$r0`..`$r15` at `0x014b`.
3. Quiesce the Falcon at `0x016b`, polling `I[0x9100]` bit 31.
4. Clear the interrupt-enable flags `ie0` / `ie1` / `ie2` and the timer/exception flag at `0x02b3`
   (`mov $r9 0x10` / `0x11` / `0x12` / `0x18`, each followed by `bclr $flags $r9`).
5. **PHASE 5** sets the trap vector `$tv = 0xeb` and clears the `$cauth` secure-fault-enable bit:
   `mov $r9 0xeb; mov $tv $r9; mov $r9 $cauth; mov $r15 -0x80001; and $r9 $r15; mov $cauth $r9`.
6. **PHASE 6** touches, in order, CSB `0x4e00` (masked `0xff000000`, then OR `0x80003000`),
   `0x10100` (OR `0x101`, spin until bit `0x100` clears, bounded at `0x400` iterations), `0x14000`
   (set `0x7fff`), `0x14100` (low 16 bits preserved, OR `0x03ff0000`), `0x14b00` (OR `0xff00`),
   then `0x10100` again (OR `0x1000`).
7. SCP self-provision via `crnd` at `0x0433`.
8. Verify SCP and scan DMEM `0x6330`..`0x6340` at `0x0463`.
9. **PHASE 9** clears `0x10100` bit `0x1000` (AND with `-0x1001`) and installs the stack canary at
   DMEM `0x6340`, taken as the first non-zero word found while scanning DMEM `0x6330`..`0x6340`.
10. `lcall 0x7f82` into `main()` at `0x04cc`; exit at `0x04d0`.

### 7.2 `main` (IMEM `0x7f82`)

`main` orchestrates, in order: `f100_field_save_restore (0x1d3b)`; privilege-level-mask and aperture
programming; `tgt_falcon_bringup (0xaa1)`; `chipid_gate (0x6a71)`; descriptor validation;
`regtable_reverse_lookup (0xd66)`; `tlb_scan_invalidate (0x14cf)`; `booter_load_wrap (0x8137)` which
calls `booter_load_wpr_main (0x22ba)`; the finalize commit `(0x1c0e)`; `report_status (0x1d0f)`; and
on success `secure_teardown (0x7e76)`.

In MAIN.2, immediately after `watchdog_set`, Booter Load writes four fixed privilege-level-mask and
aperture values in **CSB** space:

```asm
I[0x12000] = 0x11111101
I[0x12400] = 0x00000111
I[0x12600] = 0x11111111
I[0x12100] = 0x00011100
```

Each is followed by the inline fail-closed assertion, so a CSB error at any of the four wedges the
Falcon in an infinite self-branch.

`chipid_gate` reads register `0xa00` bits [28:20] and accepts only chip IDs `0x170` and `0x171`.
Strap `0x170` passes unconditionally; strap `0x171` additionally requires bit 20 of register
`0x10200` to be set, else error `0x4b`. `PMC_BOOT_0` at BAR0 `0x00000000` reads `0x170000a1` on the
CMP 170HX, so implementation ID `0x170` passes. See [GA100 silicon](../hardware/ga100-silicon.md).

`main`'s tail, exactly:

```asm
0x80fe:  r9 = sp+8 = 0xFFEC          ; DMEM
0x8101:  r10 = D[0xFFEC]
0x8103:  lcall 0x1c0e                ; finalize / set_1180f8_top_nibble
0x8107:  if r0 != 0 skip
0x810b:  r0 = r10 = D[0xFFEC]
0x810d:  mov r10, r0
0x810f:  lcall 0x1d0f                ; report_status -> MAILBOX0 = r0
0x8113:  if r0 == 0 -> 0x8119
0x8117:  exit                        ; raw HS halt
0x8119:  lcall 0x7e76                ; secure_teardown
```

**DMEM `0xFFEC` is the slot that feeds the exit status** and decides whether teardown runs. This was
settled by a hardware A/B that refuted a competing `0xFFE4` hypothesis, and matches the published
ROP v3 annotation "FFEC 00000000 <- Return value to main() to indicate success ($r0)". Setting
`D[0xFFEC] = 0xDEADBEEF` moved `0x001180f8` from `0x11000000` to `0xf1000000` exactly as the
`(r0 << 28)` model predicts.

### 7.3 What the booter actually does for the GPU

Two workloads matter beyond the GSP handoff:

- **Memory clock and timing programming.** `memcfg_program (0x79cc)` reads BAR0 `0x20414`,
  `0x136658`, `0x136e58` and `0x136458`, packs extracted bitfields and writes `0x11824c` and
  `0x118250`. `memcfg_apply_poll (0x7a64)` runs only if `0x11824c` bit 0 is set, then polls
  `0x136600`, `0x136e00` and `0x136400` with timeout 100000 (error `0xa6`).
  `memcfg_timing_program (0x7c65)` computes scaled timing and bandwidth values from a base constant
  `0x32a` derived from `0x137178` and `0x136604`, timeout 125000 (error `0xa7`).
  `const_out_write (0x797a)` supplies fixed constants `0x68`, `0x555`, `0x5be`, `0x5a0`.
- **Target Falcon bring-up.** `tgt_falcon_init_reset (0x9da)` writes `0x3f0c = 0xa0100`, fills the
  register group at `0x3f40` with eight words of `0xfeed0000` ORed with the index, then finalizes
  with `0x3f00 = 3` and `0x104 = 1`. `mailbox_write_d000 (0xb28)` polls `0xd000` for bits
  `0x1c0000`, writes data to `0xd200` and command to `0xd100`. `tgt_falcon_handshake (0xbc9)`
  validates a `0xbadf0000` sentinel and a `0x3f20`..`0x3f40` range, error `0x38`.

The finalize tail of `booter_load_wpr_main` arms the GSP RISC-V handoff: at `0x286a` the booter sets
bit 24 of `SECURE_SCRATCH_14` (`0x001180f8`) via `0x1b44`, then `0x2874` calls `reg_init (0x68ed)`,
which writes GSP `FBIF_CTL 0x00110624 = 0x90` (ALLOW_PHYS_NO_CTX bit 7 plus bit 4), `0x00110684 = 1`
and `0x0011126c = 1`. Any chain that means to hand off to GSP-RM must let this run or reproduce the
three writes. The field names of `0x110684` and `0x11126c` are inferred, not header-confirmed.

---

## 8. The DMEM map

All addresses here are **DMEM**. Nothing at all is allocated below `0x100`, which is why a "mega-ROP
staged in low DMEM" was ruled out.

| DMEM | Contents | Notes |
|---|---|---|
| `0x0000`-`0x00FF` | unallocated | |
| `0x0200` | booter's own HS signature | Patched into the image before load (`hsSigDmemAddr = patchLoc - dataOffset`, `0x8900 - 0x8700`). **Not** the buffer that overflows. |
| `0x0530` | DMA/engine config descriptor struct | |
| `0x0600`-`0x06FF` | `WprMeta`, a 256-byte struct | Magic `0x371a60b3` at +0, `0xdc3aae21` at +4. Below the DMA target, so the overflow never touches it. |
| `0x0700` | image descriptor | `ls_sig_verify` requires `r10 == 0x700` |
| **`0x0800`** | **GSP-RM LS signature buffer** | **The DMA destination. The exploit.** |
| `0x103c` onward | crypto-session descriptor | Fields `0x1004`, `0x107c`, `0x1080`, `0x1100` |
| `0x1900` | `f100` field-save slot | The shipping payload plants `0x00000007` here |
| `0x1904` / `0x190c` / `0x1914` | PTE caches for `va_to_pa_walk` | |
| `0x1a00` / `0x2a00` / `0x3a00` | page buffers | |
| `0x2383` | register descriptor table | Smashed by a `0xF800` payload; source of error `0x35` |
| `0x5f00` | firmware request header | `'FREE'` / `'HEAP'` magic |
| `0x6330`-`0x633F` | scratch scanned at PHASE 9 | |
| **`0x6340`** | **stack-canary guard global** | 25408 decimal |
| `0x8700` | end of booter code/data | |
| `0x8e08` | register descriptor table | Also smashed |
| ~`0xFF3C`-`0xFFFF` | the live call stack | Grows downward from the top |

### The stack canary

A fresh random value is generated each boot and held in the global at DMEM `0x6340`. Every protected
function copies it to the boundary of its stack frame and re-reads and compares on exit; a mismatch
calls `panic()` at `0x7dd9`. The canonical prologue is `mov $rX 0x6340; ld b32 $r9 D[$rX]`; the
epilogue is `cmp b32 $r15 $r9; bra e <ok>; lcall 0x7dd9`.

Because the value is regenerated per boot from the hardware RNG it cannot be guessed offline. It
does not need to be. The guard global lives in writable data memory reachable by the very overflow
it is meant to detect, so the payload overwrites the global **and** every reconstructed canary slot
with the same chosen value, and every epilogue compare passes. This is the published paper's
Thesis 1: the Falcon stack canary fails on *reference-word integrity*, not entropy. In this image
the toolchain emits the guard at the tail of the read-only-data section, which in the flat
MPU-mapped image lies inside the writable data span. There is no RELRO equivalent, no guard page and
no MPU read-only mapping.

---

## 9. The BAR0 master, the CSB discipline and the mailbox

### 9.1 The BAR0 master

The Falcon can reach external BAR0 registers only through an indirect, mutex-gated mailbox in Falcon
CSB space. There is no memory-mapped "direct" path.

| CSB port | Role |
|---|---|
| `I[0x1c100]` | Target PRI address (full 32 bits) |
| `I[0x1c200]` | Data. For reads, the result comes back here. |
| `I[0x1c000]` | Command: **`0x800000f2` = write, `0x800000f1` = read** |
| `I[0x1c300]` | Watchdog, seeded with `0x1312d00` (20,000,000) by `watchdog_set (0x1034)` |

The booter uses this path for its own work: `0x29b8 -> 0x10aa` writes the WPR2 registers, and the
finalize routine's write to `0x001180f8` is literally `1c4b: r10=0x1180f8 ; lcall 0x10aa`. A
corresponding read appears as `1c35: r10=0x1180f8 ; lcall 0x1196`.

### 9.2 Fail-closed CSB access

**Every CSB access in the booter is fail-closed.** After each access the code samples CSB error
status `I[0x9100]` bit 31, which is `FALCON_CSBERRSTAT.VALID`, a **fault flag** meaning the last CSB
access errored, **not** a busy or completion poll. The raw inline prologue branches to itself on
error, wedging the Falcon forever; the two helpers instead report status `0x15` and exit.

```asm
mov  rX 0x9100
iords
shr  0x1f
bra
self-lbra
```

That idiom appears about 25 times inline plus in the two helpers. `csb_read (0x8264)` additionally
masks returned data with `0xffff0000` and tests for the PRI poison sentinel `0xbadf0000`, with a
whitelist (`reg_whitelist_40f00` at `0x208c`, covering `[0x40f00, 0x41f00)` step `0x100`) and a retry
path for registers `0x1c200`, `0xc00`, `0xb00` and `0xd500`.

### 9.3 MAILBOX0 semantics

Falcon I/O `0x1000` is the Falcon's own MAILBOX0 and is host-visible at BAR0 `0x00840040`, with
MAILBOX1 at `0x00840044` (`CSB 0x1000 / 64 = falcon 0x40`). Reading BAR0 `0x1000` directly from the
host at PL0 returns `0xbadf5040`, which resolved a long-running confusion.

MAILBOX0 is the only observable channel during exploitation, and the unifying rule is:

> [!NOTE]
> **MAILBOX0 equals `$r0` on any return path that passes through `report_status`**
>
> MAILBOX0 reading `0x31` simply means `report_status` was never executed. The booter itself
> stamps `0x31` at ucode offset `0x7a` (`mov $r15 0x31 / mov $r9 0x1000 / iowrs I[$r9] $r15`) as
> its very first liveness marker, overwriting the driver's planted WprMeta physical-address
> argument.

Measured: return address `0x8117` (raw exit, skips `report_status`) gives MB0 `0x31`; `0x810d` gives
MB0 `0x0` when `r0 = 0` and `0xcafe` when `0xcafe` was planted; `0x8d4` gives `0x0b`.

Practical taxonomy: `0x47` = stack-canary check failed and the Falcon is in the `panic()` self-loop;
`0x31` = `report_status` never ran; `0x96` = booted normally with the canary intact.

### 9.4 Status codes

| Code | Source | Meaning |
|---|---|---|
| `0x01` | `antirollback_version 0x59c4` | Stored version exceeds candidate |
| `0x05` | `wpr_region_check 0x28ac` / `wpr_region_program 0x291e` | WPR limit < base, or empty region |
| `0x11` | `pka_ready_check 0x580f` / `pka_status_check 0x5473` | |
| `0x15` | `csb_read` / `csb_write` / `mailbox_wait_ready` / `reg_read_indirect` | CSB/PRI access fault |
| `0x1c` | generic | Bad argument |
| `0x23` / `0x4e` | `verify_reg_bitlen` | |
| `0x29` | `check_1180f8_nibbles 0x1c75` (called from `0x80a5`) | `0x001180f8` [31:28] or [23:20] non-zero |
| `0x2d` | `firmware_load_main` | |
| `0x31` | PC `0x7a` | Entry liveness marker; `report_status` not reached |
| `0x32` | `check_reg_4f00` | |
| `0x35` | `regtable_rw_indexed` | DMEM descriptor tables at `0x2383`/`0x8E08` read zero |
| `0x38` | `tgt_falcon_handshake 0xbc9` | |
| `0x47` | `__stack_chk_fail 0x7dd9` | Canary mismatch, then hangs |
| `0x4b` | `chipid_gate 0x6a71` | Strap `0x171` without `0x10200` bit 20 |
| `0x54` | unknown | Observed only on a PG199 board. See below. |
| `0x59` | driver-side | `dmem.bin` absent. Benign. |
| `0x5c` | `antirollback_version` | Aperture check |
| `0x62` | PKA path | |
| `0x63`-`0x6d` | `pka_modexp_run 0x54ab` | `0x6c` = timeout |
| `0x6e` | `check_10200_820434` | |
| `0x74` | `check_reg_118128` | |
| `0x88` | `check_1180f8_2724 0x1ba3` | `0x001180f8[27:24]` non-zero |
| `0x89`-`0x90` | `wpr_desc_validate 0x154a` | `0x8e`/`0x8f` are the `0x1ffff` alignment and `0xfff` field checks |
| `0x96` | normal | Booted with the canary intact |
| `0x98` | `ls_sig_verify 0x399a` / `booter_load_wpr_main` | |
| `0x9c` / `0xa4` | `booter_load_wpr_main` | |
| `0x9e` | `range_validate_windows` | |
| `0x9f` | `hw_state_gate`, `dma_region_lock_setup` | |
| `0xa5` | `firmware_load_main` | |
| `0xa6` / `0xa7` | memcfg paths | |

Host-side, for contrast: `NV_ERR_TIMEOUT = 0x00000065`, `NV_ERR_MEMORY_ERROR = 0x72`,
`NV_ERR_GENERIC = 0xffff`. Composite `RmInitAdapter` failures observed include `0x62:0x40:2028`,
`0x62:0x55` and `0x62:0x65:2674`.

> [!NOTE]
> **Open problem: Booter status `0x54`**
>
> Applying a modified cmpunlocker to a PG199 board failed with
> `s_executeBooterUcode_TU102: Booter failed 0x54` even though the CFG1 and LMR writes landed and
> the PLMs opened. Every other status code was pinned by locating its write site in the
> disassembly; the same method should work for `0x54`, and the disassembly is in hand.

---

## 10. Leaving heavy-secure mode, and the reset PLM

`secure_teardown` at IMEM `0x7e76` is the designed exit. It re-enables the `0x10100` DMA aperture
(OR `0x101`, spin until bit `0x100` clears, bounded at `0x400` iterations), sets `$cauth |= 0x80000`
(bit 19, suppressing interrupts and exceptions before halting), then for each of `$c0`..`$c7` issues
`csecret $cN 0x0` followed by `cxor $cN $cN`, loops `st b32 D[$r9] $r14; add $r9 0x4` from 0 to
`0x10000` with `r14 = 0`, clears `r0`..`r15`, and executes the raw `exit` opcode (`f8 02`). It never
returns. That `exit` is what drops the Falcon out of HS mode and allows new code to be loaded.

Reaching it from `main` requires the `r0 == 0` branch at `0x8113` to `0x8119`. If `r0` is non-zero,
`0x8117 exit` is taken and there is no teardown at all.

The **error paths always call `report_status (0x1d0f)` then `secure_teardown (0x7e76)` in that
order**: the pair appears at `0x873`/`0x877`, `0x88a`/`0x88e` and `0x8a7`/`0x8ab`. The success path
calls neither, leaving crypto and environment intact for the GSP handoff. A framing of "mailbox XOR
teardown" that circulated is therefore wrong: errors do both.

### The reset PLM, `0x008403C4`

The SEC2 reset-source PLM guards the SEC2 `FALCON_ENGINE` reset control at `+0x3c0`. Its post-fire
value decides whether SEC2 can be reset again.

| Value | Meaning |
|---|---|
| `0xff` | Fully open. Clean idle, post-SBR, SEC2 unused. A host PL0 `kflcnReset` will take. |
| `0xdf` | The normal working state a stock driver leaves after its GSP-boot teardown. Reset still permitted. |
| `0xcf` | Observed after the driver's GSP-prime re-locks the PLMs (bit 4 clear). |
| `0x8f` | The HS-exit taint. Low nibble `0xf` = all levels may read; high nibble `0x8` = write locked to the secure source, so a PL0 reset write bounces. |

Rule: `reset_allowed = resetPLM in {0xff, 0xdf}`. `0xdf = 0x8f | 0x50`.

Crucially, `0x8f` is **hardware-latched at the HS to NS exit transition**, not written by any booter
instruction: static analysis found zero instruction references to `0x8403C4` in the booter. Leaving
HS makes the hardware re-protect every HS-gated PLM to the secure default. Measured: taking the raw
exit at `0x8117` leaves resetPLM `0xff`; letting `secure_teardown` run re-latches it to `0x8f`.

> [!NOTE]
> **Open problem: does `resetPLM = 0x8f` block loading new SEC2 ucode?**
>
> One report says SEC2 is re-loadable at `0x8f` (Hello World fired, MAILBOX0 went `0x0` to
> `0x31`); another says loading a new ucode requires SFTRESET, which the reset PLM gates, and
> reports `NS load mismatch (HS-locked, needs --flr)`. The likely reconciliation, that NS reload
> works and HS-signed reload does not, was proposed but never settled. One controlled experiment
> loading an NS ucode and an HS-signed ucode back to back at a known `0x8f`, logging `CPUCTL` and
> the loader error string for each, would answer it.

The shipping driver sidesteps this whole discipline: it **never reads or writes `0x008403C4`**. A
grep of the shipping repository finds zero references to `0x008403c4`, `0x001180f8`, `0x001fa81c`
or `0x001fa820`. The in-driver path re-fires Booter Load through the driver's own
`kflcnReset`/FWSEC sequence instead, which patch `0002` confirms by logging
`SEC2_DEBUG: kflcnReset for FWSEC: 0x%x` and `SEC2_DEBUG: kflcnResetIntoRiscv: 0x%x`.

---

## 11. The signature buffer

This is the object the whole unlock turns on.

| Property | Stock | Under the unlock |
|---|---|---|
| Allocation | `NV_ALIGN_UP(pGspFw->signatureSize, 256)`; observed 4,096 bytes | `SEC2_POSTBL_TIMING_SIGNATURE_SIZE = 0x0000f800ULL` = 63,488 bytes |
| Alignment | 256 bytes, `ADDR_SYSMEM` | 256 bytes, `ADDR_SYSMEM` |
| DMEM destination | `0x0800` | `0x0800` |
| DMEM reach | `0x17FF` | `0xFFFF`, exactly the top of DMEM |
| Length source | `WprMeta.sizeOfSignature` | `WprMeta.sizeOfSignature` |

The booter takes the copy length verbatim from `WprMeta.sizeOfSignature` with no bound check of any
kind, and the driver controls both the buffer contents and that field. The enlargement is a factor
of 15.5. The stock signature's DMA reaches only DMEM `0x17FF`, which is why a normal boot leaves the
register descriptor tables at DMEM `0x2383` and `0x8E08` intact.

The DMA target `0x800` is set by `mov $r10 0x800` at IMEM `0x37ad`, followed by `lcall 0x4d4` at
`0x37b3`. See [The ROP chain](rop-chain.md) for what happens next.

> [!NOTE]
> **Not a conflict**
>
> `kernel_gsp_booter.c:329` computes `pUcode->hsSigDmemAddr = patchLoc - pUcode->dataOffset`,
> which with `patchLoc = 0x8900` and `dataOffset = 0x8700` puts a signature at DMEM `0x200`. That
> is the **booter's own HS signature**, patched into the booter image before load. DMEM `0x800` is
> where the **GSP-RM LS signature** the booter DMAs from sysmem lands, and that is the one that
> overflows. Two different buffers. Confidence: medium, in that this reconciliation is consistent
> with every observation but nobody stated it explicitly.

One more property matters for the unlock's persistence story: **the stock AES-MAC signature stays
valid after geometry changes**, because it covers the static GSP firmware image at rest, not runtime
WPR metadata or hardware geometry. WPR metadata is computed by the driver at runtime. An earlier
contrary claim was explicitly retracted by its author.

---

## 12. How the shipping driver invokes Booter Load

Everything in this section is read directly from
`driver/patches/0001-sec2-postbl-plm-ss-cfg.patch` and `0002-booter-verify.patch` on shipping
`master`. See [driver patches](driver-patches.md) for the full patch set.

### 12.1 The gate

```c
#define SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID   0x20C2
#define SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID  0x2082
```

`_kgspSec2PostblTimingEnabled()` tests `pGpu->idInfo.PCIDeviceID >> 16` against exactly those two
values. A `10de:20b0` card, which `install.sh` also greps for, installs without unlocking. Target
driver versions are `610.43.03` (default) and `610.43.02`; the build hard-fails on anything else.

### 12.2 The sequence, in order

1. **`_kgspCreateSignatureMemdesc`** allocates the signature memdesc at `0x0000f800` instead of
   `NV_ALIGN_UP(pGspFw->signatureSize, 256)`. Before repurposing it, the stock signature bytes are
   copied aside into `pKernelGsp->pStockSignatureData` / `stockSignatureSize`, two new fields added
   to `KernelGsp` in `g_kernel_gsp_nvoc.h`. Logs `SEC2_DEBUG: saved stock signature (%llu bytes)`,
   which reports 4096 on-card.
2. **Optional external payload.** `os_open_and_read_file()` tries
   `SEC2_POSTBL_TIMING_DMEM_PATH = "/lib/firmware/nvidia/ga100/gsp/dmem.bin"` into the fresh buffer.
   Success logs `SEC2_DEBUG: loaded %llu bytes from %s`; absence logs
   `SEC2_DEBUG: %s not found (0x%x), using built-in payload` with `0x59`, and falls back to the
   built-in payload pre-seeded with `writeAddr = 0x009a0148`, `writeValue = 0xffffffff`.
   `memdescFlushCpuCaches()` is called either way.
3. **Save WPR2.** Read `0x001fa824` (lo) and `0x001fa828` (hi) once, logging
   `SEC2_DEBUG: saved WPR2 lo=0x%08x hi=0x%08x`.
4. **The PLM loop.** For each of four table entries, up to two attempts:

    ```c
    for (plmIdx = 0; plmIdx < 4; plmIdx++)
        for (attempt = 0; attempt < 2 && !opened; attempt++) {
            GPU_REG_WR32(pGpu, 0x001fa824, savedWpr2Lo);
            GPU_REG_WR32(pGpu, 0x001fa828, savedWpr2Hi);
            kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp,
                                              plmTable[plmIdx].addr,
                                              plmTable[plmIdx].value);
            kgspExecuteBooterLoad_HAL(pGpu, pKernelGsp,
                memdescGetPhysAddr(pKernelGsp->pWprMetaDescriptor, AT_GPU, 0));
            regVal = GPU_REG_RD32(pGpu, plmTable[plmIdx].addr);
            opened = (regVal == plmTable[plmIdx].value);
        }
    ```

    Failure logs `SEC2_DEBUG: FAILED to open <name> after 2 attempts`. The table and its exact
    values are on [Privilege Level Masks](privilege-level-masks.md).

5. **Restore WPR2** once more after the loop.
6. **Four plain host writes at PL0**, no further exploit required:
   `0x0082381c = 0x88888888` (SS0), `0x00823820 = 0x00000008` (SS1), `0x009a0204 = cfg1Value`,
   `0x00100ce0 = lmrValue`. Then `SEC2_DEBUG: POST-WRITE SS0=… SS1=… CFG1=… LMR=…`. See
   [compute throttle](compute-throttle.md) and [memory geometry](memory-geometry.md).
7. **`kgspSec2PostblTimingRebuildStockSignature()`** frees and destroys the `0xf800` memdesc,
   allocates a replacement at `NV_ALIGN_UP(stockSignatureSize, 256)` with
   `MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY`, copies `pStockSignatureData` back, and re-points
   `pWprMeta->sysmemAddrOfSignature` / `sizeOfSignature`. Failure aborts the boot with
   `SEC2_DEBUG: rebuild stock signature failed: 0x%x`.
8. **`kgspPopulateWprMeta_HAL` runs a second time** so WPR metadata reflects the enlarged FB.
   On-card dmesg shows `WPR meta updated fbSize=0x0000001000000000 …` immediately followed by
   `normal BooterLoad status=0x0`.

This is why GSP-RM boots normally in the *same* driver load: the exploit and the real boot are
sequential within one load, and no cold-boot-equivalent handoff is needed.

### 12.3 The refill helper

`kgspSec2PostblTimingRefillPayload(pGpu, pKernelGsp, writeAddr, writeValue)` maps the memdesc with
`memdescMapInternal(..., TRANSFER_FLAGS_NONE)`, rewrites the entire `0xf800`-byte payload for that
one `(writeAddr, writeValue)` pair, unmaps, calls `memdescFlushCpuCaches()` on the signature
memdesc, republishes `pWprMeta->sysmemAddrOfSignature = memdescGetPhysAddr(...)` and
`pWprMeta->sizeOfSignature = memdescGetSize(...)`, then flushes CPU caches on `pWprMetaDescriptor`.
It returns `NV_ERR_INVALID_STATE` if the memdesc is NULL and `NV_ERR_INSUFFICIENT_RESOURCES` if the
map fails. Handing the booter a signature length of `0xf800` **is** the overflow.

The cache flush is not optional. The signature DMA is non-coherent, and without an explicit flush
the Falcon reads stale RAM.

### 12.4 Two accommodations the patch makes

- **WPR2 already up.** The fatal path

    ```c
    NV_PRINTF(LEVEL_ERROR, "unexpected WPR2 already up, cannot proceed with booting GSP\n");
    return NV_ERR_INVALID_STATE;
    ```

    becomes `NV_PRINTF(LEVEL_WARNING, "WPR2 already up before GSP boot; continuing for recovery\n")`.
    Repeated booter fires leave WPR2 up, and each fire re-carves it. The empty/INIT state is
    LO `0x0fffffff`, HI `0`, and **HI = 0 makes `kgspIsWpr2Up()` return false**. The shipping driver
    restores the *saved* pair rather than writing an empty region.

- **`0002-booter-verify.patch`** converts several `NV_ASSERT_OK_OR_RETURN` sites in
  `kgspBootstrap_TU102` into logged status checks and adds a post-BooterLoad readback of five
  registers for device IDs `0x20C2` / `0x2082`:

    ```c
    #define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_PLM        0x00823804
    #define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED   0x0082381c
    #define SEC2_DEBUG_PRI_FEATURE_OVERRIDE_SM_SPEED_1 0x00823820
    #define SEC2_DEBUG_PRI_FBPA_CFG1                   0x009a0204
    #define SEC2_DEBUG_PRI_MMU_LMR                     0x00100ce0
    ```

### 12.5 How many times the booter runs

| Case | Booter Load fires |
|---|---|
| Every PLM opens on the first attempt | 4 exploit fires + 1 normal boot = **5** |
| Every PLM needs both attempts | 8 exploit fires + 1 normal boot = **9** |

Exactly **one** arbitrary BAR0 write is performed per fire.

### 12.6 Reading the logs

> [!WARNING]
> **Register readback is the only valid success criterion**
>
> Every payload execution logs
> `s_executeBooterUcode_TU102: Booter failed with non-zero error code: 0x31` and
> `kgspExecuteBooterLoad_TU102: failed to execute Booter Load: 0xffff`, **and the register writes
> still land**. In `s_executeBooterUcode_TU102` the seccode error sits in MAILBOX0 after every run
> and `mailbox0 != 0` returns `NV_ERR_GENERIC` (`0xffff`). The shipping loop's success test is
> exact readback equality, which is the right test. The project README says the same thing:
> Booter status codes such as `0x31` / `0xffff` during the early PLM passes are often harmless if
> the final boot succeeds.

See [verify](../procedures/verify.md) and [troubleshooting](../procedures/troubleshooting.md).

## 13. Driverless invocation, for contrast

A family of standalone Python and C tools (`refire_chain_v2.py` through `v9.py`,
`load_gsp_sec2_falcon.c`, `load_custom_bin.py`) fires the booter with no NVIDIA driver present.
These are **not** in the shipping repository, and most apparent contradictions in this domain
dissolve once the two code bases are kept apart. The tooling matters because it is where most of the
register discipline was learned. See [tool lineage](../history/tool-lineage.md).

Running non-secure code on SEC2 is trivial and needs nothing beyond public documentation: DMA the
binary into IMEM, set `BOOTVEC`, issue `STARTCPU`, then poll `CPUCTL` bit 4 (HALTED) if the code uses
`exit`. The full driverless boot sequence is: engine reset, wait for DMA scrub, `ALLOW_PHYS_NO_CTX`,
physical DMA aperture, DMA IMEM + DMEM, set `BOOTVEC`, set mailboxes, `STARTCPU`, poll HALTED.

The reset sequence, as implemented and working:

```text
if SCTL (SEC2+0x240) has HSMODE (bit 1) set:
    write SFTRESET (SEC2+0x07c) = 1 and read back
pulse ENGINE (SEC2+0x3c0): 1 then 0
poll DMACTL (SEC2+0x10c) until scrub bits 0x6 clear, ignoring 0xffffffff reads
poll SCP_P2PRX (SEC2+0x530) bit 3, with KFUSE_CTL (SEC2+0x11ec) bit 0 set and bit 1 clear
OR AUTH_EN (1 << 14) into SCTL
```

Default timeout is 10.0 s; the failure path reports "scrub timeout". Booter loading then uses
IMEMC/IMEMD with auto-increment and per-256-byte IMEM tags, with the SECURE bit `1 << 28` set for
the HS region. Apertures are forced to physical mode by writing `FBIF_TRANSCFG[0..2] = 4, 5, 6` at
`0x00840600`/`0x604`/`0x608` and then `FBIF_CTL |= 0x80` at `0x00840624`, before `start_wait` with
MAILBOX0/1 set to the low and high halves of the WprMeta physical address.

A standalone C program executed the full nine-step driverless boot on hardware and read a halt
return value of `0xb` from `FALCON_MAILBOX0`: the load path worked with no NVIDIA driver present,
even though the Falcon halted with a non-zero status.

Two further requirements the driverless path discovered, both of which the shipping driver satisfies
by other means:

- **Cache flush.** A 17-byte JIT-assembled x86-64 stub
  (`0F AE 3F 48 83 C7 40 48 83 EE 40 7F F3 0F AE F0 C3`, i.e. `clflush [rdi]` / `add rdi,64` /
  `sub rsi,64` / `jg` / `mfence` / `ret`) is mapped `PROT_EXEC` and run over the payload, radix3 and
  WprMeta buffers, rounded up to 64-byte cache lines. `refire_chain_v6.py` allocates 2 MiB hugepages
  with `MAP_HUGETLB` (`0x40000`), mlocks them, and resolves the physical address from
  `/proc/self/pagemap` by checking the present bit then `(entry & ((1<<55)-1)) * 4096`.
- **A minimal radix3 page table.** `stage_radix3()` allocates `0x6000` bytes and writes three 64-bit
  descriptors (PDE2 at `0x0000` to `phys+0x1000`, PDE1 at `0x1000` to `phys+0x2000`, PDE0 at
  `0x2000` to `phys+0x3000`), leaving the data page and bootloader body zeroed, then flushes.
  Without it the booter's pre-signature DMAs fail with cause `0x9`. The WprMeta template is 256 bytes
  captured from a real 10 GB boot, with only the radix3 pointer (`+0x10`), radix3 size (`+0x18`),
  bootloader pointer (`+0x20`), bootloader size (`+0x28`), signature pointer (`+0x48`) and
  signature size (`+0x50`, set to `0xF800`) overridden.

Note that the two paths also differ in mailbox semantics: the standalone loader polls HALTED with a
5 s timeout and then reads `0x840040` expecting `0x31` / `0x96` / `0x47`, whereas the in-driver path
reports `0xffff` regardless of outcome.

---

## 14. Open problems on this page

> [!NOTE]
> **Can a driverless fire hand off to a stock driver at all?**
>
> The stock driver's booter rejects post-fire SEC2 state via the classic two-load "mutex horns":
> `0x31` (mutex held), `0x62` (WPR2 up) and `0x29` (a `0x001180f8` error, because the `mutexfree`
> terminator leaves `0xf0000000` and the `0xf` top nibble trips the check). This fails even at
> 10 GB with consistent geometry, proving it is the SEC2 / `0x001180f8` handoff state the fire
> perturbs, not the geometry and not the write count. Two fixes were proposed: make the terminator
> leave the `0x001180f8` top nibble zero, or stage geometry from inside a patched driver. **The
> shipping unlocker took the second.**

> [!NOTE]
> **Crossing the RmInitDone wall without an FLR**
>
> The `whole_stack_rejoin` terminator restarts SEC2 after the exploit with no FLR and gets the
> booter to complete and the GSP-RM RISC-V core to start, but init never completes. This is the
> same `0x65` boot wall. `0x001180f8` is `NV_PGC6_BSI_SECURE_SCRATCH_14`, bit 26 is
> `BOOT_STAGE_3_HANDOFF` (INIT = 0, DONE = 1), and only SEC2 in HS sets it. Pre-writing DONE does
> not help: the read path is PLM-poisoned so `0x001180f8` reads back `0xdead5ec1`, and on a
> poisoned read bit 26 already reads as 1, producing a false DONE that kills GSP-RM later instead.
> The two candidate root fixes are to preserve the booter success path so SEC2 primes its RTOS and
> sets DONE itself, or to restore the AON `SECURE_SCRATCH` PLM/priv state, which today only a
> power-domain reset achieves.

> [!NOTE]
> **Porting to other CMP cards**
>
> The CMP 50HX is TU102 and uses a completely different memory access-control register set. The
> CMP 90HX is GA102 with 10 GB GDDR6X and no extra physical memory, so only a compute unlock would
> be meaningful. The stated rule is that the same Turing booter, script and exploit apply to any
> card whose SEC2 accepts the Turing-generation AES and RSA keys. One tester reported the TU10x
> `booter_load` loading on a GA102 CMP 90HX with SS0/SS1 PLM writes succeeding, while
> self-qualifying that the written values "were not right" and warning that one positive test is
> not enough. A separate static analysis of a GA102 booter concluded there is no overflow point
> because the size is strictly validated. Nobody ran the decisive test: load the TU10x booter on a
> GA102 and attempt a known-good single PLM write with readback.

> [!NOTE]
> **Windows and non-Linux**
>
> The vulnerability is in GPU firmware and is not OS-dependent. Current implementations are Linux,
> and neither a Unix host nor the open driver is a hard requirement, but a Windows port was
> described as far more than a few lines of work.

> [!NOTE]
> **Recovering a `csecret`**
>
> Three indices map to three capabilities: `secret(6)` decrypts the ECB firmware blobs (would
> yield 121.7 KB of plaintext firmware plus Booter code); `secret(2)` forges the content MAC
> (prerequisite for both the CFG1 memory unlock and the PCIe speed unlock by that route);
> `secret(0)` is the debug bypass enabling a HULK cert with `SKIP_VBIOS_SIG`. **No csecret has
> been recovered.** All three remain differential-fault-analysis targets requiring voltage-glitch
> hardware. Without the **Booter decryption key** the encrypted booter cannot be rebuilt (only
> read, via the debug-key route); without the **VBIOS debug key** the VBIOS cannot be re-signed or
> run in debug mode. The current unlock works around both by reusing the stock signed booter as an
> execution engine.

> [!NOTE]
> **A second instance of the same bug class**
>
> The paper (section 5.5) notes that GSP-RM's own resident blob carries a second instance of the
> same bug class, where the guard global is a **public hardcoded constant** rather than
> RNG-seeded. No address is published, no exploit was built on it, and nobody in the archive
> verified it.

### Documented negative results

- **`envytools` cannot corroborate any of this.** Its Falcon crypto page has section headings for
  Introduction, IO registers, Interrupts, "Submitting crypto commands: ccmd", "Code authentication
  control" and "Crypto xfer control", **every one marked "Todo: write me"**. There is no
  documentation of the AES engine, key handling, signed code authentication, secure mode entry or
  exit, code page signature checking, or any CMAC/CBC-MAC scheme. Recorded so nobody re-searches it.
  envytools also documents Falcon hardware only up to v5 (GK208+) and contains no Ampere or GA100
  coverage; its register maps (`UC_CTRL 0x100`, `UC_ENTRY 0x104`, `UC_CAPS 0x108`, `UC_STATUS 0x128`,
  `CODE_INDEX 0x180`, `CODE 0x184`, `DATA_INDEX[0-7] 0x1c0`, `SCRATCH0 0x040`) are structural
  background only and must **not** be used to validate GA100 register addresses.
- **Re-entering the booter by returning to `_start` at IMEM `0x100`** with two signatures in a row
  was tested and failed with the same `0x31` in the mailbox. The low-secure bootstrap at `0x00` is
  wiped when the Falcon enters HS mode, so there is nothing to return to.
- **Harvesting live SCP secrets by skipping `secure_teardown`** was refuted the day it was proposed
  by two adversarial byte-for-byte static traces: the prologue at `0x107`-`0x147` self-XORs each
  secret to zero immediately, the real key use is the AES verify at `0x1e20`-`0x1e70`, scrub sweeps
  at `0x1e74`-`0x206e` run three back-to-back self-zero passes, and the last crypt op is
  `0x206e cxor $c0, $c0`. From `0x2070` to `0x7eef` there are **zero** crypt ops, and the hijack
  point (`lcall 0x4d4` at `0x37b3`) sits squarely inside that crypt-silent gap. The skip saves
  nothing because the bank is already empty about 0x1500 bytes of code earlier.
- **Reversing the booter to obtain HS signing privileges** was dropped by its own proposer. Even
  extracting the AES key from silicon leaves the RSA private key missing: the die holds only the
  public key. The remaining theoretical route is enabling debug mode and using the debug RSA private
  key, but a physical fuse disables debug mode on production cards and only engineering samples have
  it enabled.
- **Host-side PCI device-ID spoofing to an A100 ID (`0x20b0`)** cannot work: VBIOS/devinit keys off
  the card-level device ID before the driver or GSP get a chance to, and it is the same booter for
  all GA100 cards and even Turing cards, so nothing downstream branches on the host ID.

---

## Related pages

- [How the unlock works, end to end](how-it-works.md)
- [The ROP chain](rop-chain.md)
- [Privilege Level Masks](privilege-level-masks.md)
- [Driver patches](driver-patches.md)
- [Register reference](register-reference.md) and the [register index](../appendix/register-index.md)
- [Glossary](../start/glossary.md)
- [Dead ends](../history/dead-ends.md)
