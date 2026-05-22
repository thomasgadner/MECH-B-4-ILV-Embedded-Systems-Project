import sys
import serial
import time
import random

dev = sys.argv[1]

ser = serial.Serial(dev, 9600, timeout=1)

def send_frame(msgid, payload):
    frame = b'#' + msgid.encode()
    frame += bytes([len(payload)])
    frame += payload
    crc = sum(frame[1:]) & 0xFF
    frame += bytes([crc]) + b'$'
    ser.write(frame)
    ser.flush()

def recv_frame():
    while ser.read(1) != b'#':
        pass

    msgid = ser.read(3).decode()
    length = ser.read(1)[0]
    payload = ser.read(length)
    ser.read(1)
    ser.read(1)

    return msgid, payload

time.sleep(1)

send_frame("STR", b"RL")
recv_frame()

send_frame("CSH", b"1711636203")

while True:
    msgid, payload = recv_frame()

    if msgid == "BOO":

        # Random hit/miss
        send_frame("BMR", b"H" if random.random() > 0.7 else b"M")

        # Random fire
        send_frame(
            "BOO",
            bytes([
                random.randint(0, 9),
                random.randint(0, 9)
            ])
        )

        recv_frame()