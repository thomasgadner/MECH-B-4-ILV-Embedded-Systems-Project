import sys
import serial
import time

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

x = 0
y = 0

while True:
    msgid, payload = recv_frame()

    if msgid == "BOO":

        # Host always misses
        send_frame("BMR", b"M")

        # Sweep entire board systematically
        send_frame("BOO", bytes([x, y]))
        recv_frame()

        y += 1
        if y >= 10:
            y = 0
            x += 1

        if x >= 10:
            break