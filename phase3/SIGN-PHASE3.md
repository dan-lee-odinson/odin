# Phase 3: what the Director signs, in one sitting (drafted by Claude Code, 30 October 2026)

Held out: this folder never goes to Muse Code, VERDA, the render session or Modal.

Twenty-two files: the seven phase-3 plans (namespace `tyr0`), the five arming acts and the ten restore acts
(namespace `aesir-arm`). Each `ssh-keygen -Y sign` writes `<file>.sig` beside the file it signs.

- The plans are byte-identical copies of the sealed ones, in `plans-to-sign\`: a signature written inside
  `sealed\` would be a file the sealed manifest does not list, and the seal check would refuse every run.
  The phase-3 runner takes each plan's bytes from the seal-checked folder and its signature from here.
- The acts are signed where they are, in `acts\`.

Before signing, check any file against the SHA-256 below (`Get-FileHash <file>`).

## The files

| File | Namespace | SHA-256 |
|---|---|---|
| plans-to-sign\TYR0-H01-C1-v1.yaml | tyr0 | f059bc8ce95f4c1b72f44b9b81ce1bcd0eb0b0861f3d1a59d2f1cf8b3f0f5ced |
| plans-to-sign\TYR0-H01-C2-v1.yaml | tyr0 | 6741ac805770657cb3f576fd31dcf208a85ff9da16fdbb8351f9c2092767dcb5 |
| plans-to-sign\TYR0-H02-C1-v1.yaml | tyr0 | 2db4de5cf4b6c243dec68896835425eb7b323f28c4729f9e004d327e9de85369 |
| plans-to-sign\TYR0-H03-C1-v1.yaml | tyr0 | 852612a43c4800041773408f67b376975e07cac45bcd11dda82a2839cd9a8381 |
| plans-to-sign\TYR0-H03-C2-v1.yaml | tyr0 | a5d0ac5df8f8cd07d73b12141fd3c5a3c80c94f7e80ed051c3c47a2ec90becac |
| plans-to-sign\TYR0-H04-C1-v1.yaml | tyr0 | f7923c53f84e311ee57829316ace73519de5223eae2bbc80145e4cbb22db98ff |
| plans-to-sign\TYR0-H05-C1-v1.yaml | tyr0 | 43f5908948d52a6baf1427f7cd427bd0e2aef8c86d2e0c2cc5eb1fd3d6a71e93 |
| acts\ARM-PH3-H01.yaml | aesir-arm | 5a2e0e2fe716104125150638b6abc1e1f69bd0f1e21f15686edfaae62f3bf050 |
| acts\ARM-PH3-H02.yaml | aesir-arm | f3879447aa5ffb6d921c543848e2bec40b4ce3bb1d2cefbf915db5bf49f6453f |
| acts\ARM-PH3-H03.yaml | aesir-arm | be8c67b8e7246b4f3fff4e914714f3e35d24f9bd8dc22861471d1c8d1636f078 |
| acts\ARM-PH3-H04.yaml | aesir-arm | 4637dd4ae4bdfd7fa4362f254bb9298ec03eabce811511518c279ae923fcafeb |
| acts\ARM-PH3-H05.yaml | aesir-arm | 356eda00f07ee13b76610c6184764386751d3f8ab46ab241a6654a03a789a2be |
| acts\RST-PH3-H04-OPEN-R1.yaml | aesir-arm | e0e850bc26ea78b3afa5684804beda9030ca0b24b4c7eda1f4ed65244e4af88b |
| acts\RST-PH3-H04-OPEN-R2.yaml | aesir-arm | 3850f56208147edf19184e0b63daae4af92be1cc7544a4c64197b4419fa5c0f1 |
| acts\RST-PH3-H04-OPEN-R3.yaml | aesir-arm | 835c8458745c2b0b2bd8f36c52b0d0cb207d608b372a06ec94be16f222f2e128 |
| acts\RST-PH3-H04-OPEN-R4.yaml | aesir-arm | ba1b0e31a517301273284f76908e6e6564e8837b2525a6dd1e165962f6ee88f5 |
| acts\RST-PH3-H04-OPEN-R5.yaml | aesir-arm | b54f9b7a3a295cacad81028899489bbdf851b1810cceb68834c7b22347334c64 |
| acts\RST-PH3-H04-SPARK-R1.yaml | aesir-arm | 4c4e96dfbd843492efa44f27b3da861b44533dd36b410c71efdbb781bd3f4e02 |
| acts\RST-PH3-H04-SPARK-R2.yaml | aesir-arm | 3ee0ef3dc101e599c31dea2d7dd7616783407724720ed925835faba0a44db592 |
| acts\RST-PH3-H04-SPARK-R3.yaml | aesir-arm | fa037afd36759a247f26853ace40aa3240f0eb84520f6c689694ef650979a674 |
| acts\RST-PH3-H04-SPARK-R4.yaml | aesir-arm | e813a04f8ec69b8aef623080bc2d76e5f6c5e68d07c999363ff18d26188edb02 |
| acts\RST-PH3-H04-SPARK-R5.yaml | aesir-arm | 850132fb70d8305b4a834b68170b6df37ebe4e1233ccbd9bc0c6b776af57c060 |

## The commands (PowerShell, from this folder)

Set your TYR-0 private key's path once, then run the two blocks:

```powershell
$key = "<path to your TYR-0 private key>"
```

```powershell
Get-ChildItem plans-to-sign\TYR0-*.yaml | ForEach-Object { ssh-keygen -Y sign -f $key -n tyr0 $_.FullName }
```

```powershell
Get-ChildItem acts\ARM-PH3-*.yaml, acts\RST-PH3-*.yaml | ForEach-Object { ssh-keygen -Y sign -f $key -n aesir-arm $_.FullName }
```

Then tell Claude Code. It checks every signature with `ssh-keygen -Y verify -f keys\allowed_signers -I dan` under
the right namespace, and that no signed file changed by a byte.

## 31 October 2026: the re-flies of PH3-H03-SPARK-R1, R2 and R3, signed together (drafted by Claude Code)

Three runs of C's SPARK arm re-fly, last, after D:
- **PH3-H03-SPARK-R1.** S8 set it aside for LINK_LOST, a defect of ours, fixed on 31 October by the Director's ruling
  "Approve all three, with conditions". His overnight order: "R1 re-fly after I sign". It re-flies as
  **PH3-H03-SPARK-R6**.
- **PH3-H03-SPARK-R2.** A Windows Update restart of the machine interrupted it at MET 12485, and nothing is scored for
  it. His ruling: "Record it; re-fly as R7, last, after I sign". It re-flies as **PH3-H03-SPARK-R7**, after R6.
- **PH3-H03-SPARK-R3.** S8 set it aside for LINK_LOST: COSMOS, on the first run after the machine's restart, showed its
  first frame 0.516 s late. His ruling: "Lift it; warm COSMOS first; re-fly R3 as R8". It re-flies as
  **PH3-H03-SPARK-R8**, after R7.

As phase 1's re-flies were (ARM-PH1-R2 to R4), each re-fly is the arm's next run, armed by an act of its own that
names only it. ARM-PH3-H03 is unchanged. The phase-3 runner takes runs R1 to R5 only, so it needs a change to take R6
to R8 (and R9, below) and their acts' names. Claude Code makes that change after D's last run, with its tests, red cases, the full
suite and the dry run, and commits it before the re-flies.

Three files, signed where they are:

| File | Namespace | SHA-256 |
|---|---|---|
| acts\ARM-PH3-H03-SPARK-R6.yaml | aesir-arm | cfd8362178756792d435c7beedb10b9af15b6853f6d188636167e2d9c7fbfc35 |
| acts\ARM-PH3-H03-SPARK-R7.yaml | aesir-arm | 4818f619f5685a1b3343aa11b61af5902560b4f7597d31a92461c6abd9a1a3eb |
| acts\ARM-PH3-H03-SPARK-R8.yaml | aesir-arm | 1904c87999afc62deecf6312290a4be65d4a98a3e74abb2d52c2de5a1b0c66cb |

Their plan hashes are ARM-PH3-H03's, TYR0-H03-C1-v1 and TYR0-H03-C2-v1, and they expire when the others do.

```powershell
$key = "<path to your TYR-0 private key>"
```

```powershell
Get-FileHash acts\ARM-PH3-H03-SPARK-R6.yaml, acts\ARM-PH3-H03-SPARK-R7.yaml, acts\ARM-PH3-H03-SPARK-R8.yaml
ssh-keygen -Y sign -f $key -n aesir-arm acts\ARM-PH3-H03-SPARK-R6.yaml
ssh-keygen -Y sign -f $key -n aesir-arm acts\ARM-PH3-H03-SPARK-R7.yaml
ssh-keygen -Y sign -f $key -n aesir-arm acts\ARM-PH3-H03-SPARK-R8.yaml
```

Then tell Claude Code. It checks each signature under `aesir-arm` and each act's bytes, runs each re-fly's check, and
flies R6, then R7, then R8.

The Director signed all three on 31 October 2026. Claude Code verified each signature under `aesir-arm` for dan at
13:14Z, and each act's bytes against the hashes above.

## 31 October 2026: the re-fly of PH3-H03-SPARK-R5 (drafted by Claude Code)

- **PH3-H03-SPARK-R5.** S8 set it aside for MODEL_CALL_ERROR: five of Glimmer's calls in a row, turns 49 to 53, came
  back ERROR between 13:53:17Z and 13:53:20Z. His ruling: "Yes: R9 last, after R8". It re-flies as
  **PH3-H03-SPARK-R9**, after R8.

Its act is the same as R8's apart from its name and run. The runner change after D takes R6 to R9, each under its own
act.

| File | Namespace | SHA-256 |
|---|---|---|
| acts\ARM-PH3-H03-SPARK-R9.yaml | aesir-arm | 49fcfe2aaefc7e4481ba30e15c3df35ad32a0ff41e4d91998dffeb36e9a4eb6a |

```powershell
$key = "<path to your TYR-0 private key>"
```

```powershell
Get-FileHash acts\ARM-PH3-H03-SPARK-R9.yaml
ssh-keygen -Y sign -f $key -n aesir-arm acts\ARM-PH3-H03-SPARK-R9.yaml
```

Then tell Claude Code. It checks the signature under `aesir-arm` and the act's bytes, runs the re-fly's check, and
flies R9 after R8.
