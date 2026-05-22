import sys
import serial
import time

dev = sys.argv[1]

ser = serial.Serial(dev, 9600, timeout=1)

def send_frame(msgid, payload):
    frame = b'#' + msgid.encode('ascii')
    frame += bytes([len(payload)])
    frame += payload

    crc = sum(frame[1:]) & 0xFF
    frame += bytes([crc]) + b'$'

    ser.write(frame)
    ser.flush()

    print("SENT:", msgid, payload)

def recv_frame():
    while ser.read(1) != b'#':
        pass

    msgid = ser.read(3)
    length = ser.read(1)[0]
    payload = ser.read(length)
    crc = ser.read(1)
    eof = ser.read(1)

    print("RECV:", msgid, payload)

    return msgid.decode(), payload

# --- Handshake ---

time.sleep(1)

send_frame("STR", b"RL")
recv_frame()  # receive CSH

send_frame("CSH", b"2455314312")

# --- Gameplay loop ---

while True:
    msgid, payload = recv_frame()

    if msgid == "BOO":
        x = payload[0]
        y = payload[1]

        print(f"Opponent fired at {x},{y}")

        # Always MISS
        send_frame("BMR", b"M")

        # Fire back at random position
        send_frame("BOO", bytes([0, 0]))

        # Receive their hit/miss answer
        recv_frame()