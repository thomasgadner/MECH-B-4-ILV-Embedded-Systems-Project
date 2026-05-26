# Embedded Systems Battleship Protocol

Python reference implementation of a serial-based Battleship game protocol for embedded systems projects.

The script communicates with another device (e.g. STM32 board) over UART using a framed binary protocol with CRC protection.

---

## 🚀 Features

- Random Battleship field generation
- UART communication using framed messages
- CRC-8/SMBUS validation
- Cross-platform serial support (Linux & Windows)
- Tournament mode for automated testing
- Validation of opponent ship placement
- Cheat detection and protocol consistency checks
- Raw serial debugging support

---

# 📦 Requirements

- Python 3.x
- pyserial

Install dependencies:

```bash
pip install pyserial
```

---

# ▶️ Running the Script

```bash
python schiff.py <serial_device> [options]
```

## Serial Device Examples

| Platform | Example |
|----------|---------|
| Linux | `/dev/ttyUSB0` |
| Windows | `COM23` |

---

# ⚙️ Command Line Arguments

| Argument | Description |
|---|---|
| `ser_dev` | Serial device path |

## Optional Arguments

| Option | Description |
|---|---|
| `-v`, `--verbose` | Enable verbose debug logging |
| `-s`, `--single` | Play exactly one game |
| `-n`, `--notimeout` | Disable serial timeout handling |
| `-t`, `--tournament` | Run 100 automated games |
| `--raw-debug` | Print raw UART bytes sent and received |

---

# 💻 Example Usage

## Linux

```bash
python schiff.py /dev/ttyUSB0 -v
```

## Windows

```bash
python schiff.py COM23 --verbose
```

## Tournament Mode

```bash
python schiff.py COM23 --tournament
```

---

# 🎮 Game Rules

The game uses a standard 10x10 Battleship field.

## Ship Configuration

| Ship Length | Count |
|---|---|
| 5 | 1 |
| 4 | 2 |
| 3 | 3 |
| 2 | 4 |

Rules:

- Ships may only be placed horizontally or vertically
- Ships may not touch each other
- Surrounding cells must contain water

---

# 📡 Serial Protocol

Communication uses framed binary packets.

## Frame Format

```text
[HEADER][MSG_ID][LEN][PAYLOAD][CRC][EOF]
```

| Field | Size | Description |
|---|---|---|
| HEADER | 1 byte | `#` |
| MSG_ID | 3 bytes | ASCII message identifier |
| LEN | 1 byte | Payload length |
| PAYLOAD | variable | Message payload |
| CRC | 1 byte | CRC-8/SMBUS |
| EOF | 1 byte | `$` |

---

# 🔐 CRC

CRC configuration:

- Polynomial: `0x07`
- Init: `0x00`
- No reflection
- No final XOR

Compatible with STM32 hardware CRC configured for CRC-8.

---

# 📨 Protocol Messages

| Message | ID | Description |
|---|---|---|
| START | `STR` | Begin game |
| CHECKSUM | `CSH` | Ship count checksum |
| SHIP FIELD | `SFR` | Full ship field row |
| BOOM | `BOO` | Fire at coordinates |
| BOOM RESULT | `BMR` | Hit or miss result |

---

# 📋 Message Details

## START (`STR`)

Starts a game session.

Payload:
- Optional ASCII player name

Example:

```text
STR ""
```

---

## CHECKSUM (`CSH`)

Contains 10 ASCII digits.

Each digit represents the number of occupied cells in one row.

Example:

```text
2332421607
```

---

## SHIP FIELD (`SFR`)

Used after game completion.

Payload format:

```text
[row_index][10 ASCII digits]
```

Example:

```text
\x03 0000200000
```

Meaning:
- Row 3
- Ship part at column 4

---

## BOOM (`BOO`)

Fire at coordinates.

Payload:

```text
[row][column]
```

Example:

```text
\x03\x04
```

Meaning:
- Fire at row 3, column 4

---

## BOOM RESULT (`BMR`)

Returns hit or miss status.

| Value | Meaning |
|---|---|
| `H` | Hit |
| `M` | Miss |

---

# 🧠 Internal Components

## `SerialIO`

Handles:

- UART communication
- Frame encoding/decoding
- CRC validation
- Timeouts

---

## `Field`

Responsible for:

- Random ship placement
- Shot handling
- Ship validation
- Exporting field records

---

## `StateMachine`

Implements the Battleship protocol flow:

1. Start handshake
2. Exchange checksums
3. Gameplay loop
4. Endgame validation

---

## `FireSolution`

Base class for targeting strategies.

Current implementation:

```python
StupidFireSolution
```

Uses random coordinates.

---

# 🛡️ Validation & Cheat Detection

The script validates:

- Ship counts
- Ship sizes
- Straight ship placement
- Non-overlapping ships
- Water surrounding ships
- Correct hit/miss responses
- Valid checksum data

Protocol violations raise runtime errors.

---

# 📊 Tournament Mode

Tournament mode automatically plays 100 games.

Output characters:

| Character | Meaning |
|---|---|
| `w` | We won |
| `l` | We lost |
| `a` | Aborted |

Final statistics are printed at the end.

---

# 🐞 Debugging

Verbose logging:

```bash
python schiff.py COM23 -v
```

Raw serial debugging:

```bash
python schiff.py COM23 --raw-debug
```

Shows transmitted and received UART bytes in hexadecimal format.

---

# 📄 License

Educational / project use.