# C-BSc-Embedded-Systems Final Project


## 🚀 Usage

This project includes a Python script that interfaces with serial devices. It supports both Linux and Windows platforms.

### Requirements

- Python 3.x
- Access to a serial device (e.g., USB-to-serial adapter)

### Running the Script

```bash
python schiff.py <serial_device> [options]
```

| Argument  | Description                                                              |
| --------- | ------------------------------------------------------------------------ |
| `ser_dev` | Serial device path: e.g. `/dev/ttyUSB0` on Linux, or `COM23` on Windows. |


| Option               | Description                                         |
| -------------------- | --------------------------------------------------- |
| `-v`, `--verbose`    | Enable verbose logging (debug mode).                |
| `-s`, `--single`     | Run in single operation mode.                       |
| `-n`, `--notimeout`  | Disable timeout handling.                           |
| `-t`, `--tournament` | Enable tournament mode (specific project behavior). |


### Linux
```bash
python schiff.py /dev/ttyUSB0 -v
```

### Windows
```bash
python schiff.py COM23 --verbose
```
