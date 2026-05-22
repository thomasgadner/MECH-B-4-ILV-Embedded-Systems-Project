import sys
import serial
import time
import random

dev = sys.argv[1]
ser = serial.Serial(dev, 9600, timeout=5)

FIELD_SIZE = 10
original_field = [[0] * FIELD_SIZE for _ in range(FIELD_SIZE)]
# ---------------- FRAME HANDLING ----------------

def calc_crc(data: bytes) -> int:
    return sum(data) & 0xFF


def send_frame(msgid: str, payload: bytes):
    frame = b'#' + msgid.encode()
    frame += bytes([len(payload)])
    frame += payload
    crc = calc_crc(frame[1:])
    frame += bytes([crc])
    frame += b'$'
    ser.write(frame)
    print(f"TX: {msgid} {payload}")


def recv_frame():
    while True:
        b = ser.read(1)
        if not b:
            raise TimeoutError("timeout waiting for start byte")
        if b == b'#':
            break

    header = ser.read(4)
    msgid = header[:3].decode()
    length = header[3]

    payload = ser.read(length)
    ser.read(1)  # crc
    ser.read(1)  # $

    print(f"RX: {msgid} {payload}")
    return msgid, payload


# ---------------- FIELD + SHIPS ----------------

nr_ships = {
    5: 1,
    4: 2,
    3: 3,
    2: 4,
}

field = [[0] * FIELD_SIZE for _ in range(FIELD_SIZE)]
ships = {}
ship_id = 1


def compute_cs(field):
    result = ""
    for row in field:
        count = sum(1 for v in row if v != 0)
        result += str(count % 10)
    return result


def is_area_free(x, y):
    """Check 1-cell border around position (no touching rule)."""
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < FIELD_SIZE and 0 <= ny < FIELD_SIZE:
                if field[nx][ny] != 0:
                    return False
    return True


def can_place_ship(x, y, length, orientation):
    coords = []

    for i in range(length):
        nx = x + i if orientation == 'V' else x
        ny = y + i if orientation == 'H' else y

        if nx >= FIELD_SIZE or ny >= FIELD_SIZE:
            return False, []

        if field[nx][ny] != 0:
            return False, []

        coords.append((nx, ny))


    # ✅ check full bounding box (including border)
    for cx, cy in coords:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                nx = cx + dx
                ny = cy + dy

                if 0 <= nx < FIELD_SIZE and 0 <= ny < FIELD_SIZE:
                    if field[nx][ny] != 0:
                        return False, []

    return True, coords


def place_ships():
    global ship_id

    for length, count in nr_ships.items():
        for _ in range(count):
            placed = False

            while not placed:
                orientation = random.choice(['H', 'V'])

                if orientation == 'H':
                    x = random.randint(0, FIELD_SIZE - 1)
                    y = random.randint(0, FIELD_SIZE - length)
                else:
                    x = random.randint(0, FIELD_SIZE - length)
                    y = random.randint(0, FIELD_SIZE - 1)

                valid, coords = can_place_ship(x, y, length, orientation)

                if valid:
                    for cx, cy in coords:
                        field[cx][cy] = ship_id
                        original_field[cx][cy] = length

                    ships[ship_id] = {
                        "coords": coords,
                        "hits": set()
                    }

                    ship_id += 1
                    break
                
place_ships()




def all_ships_destroyed():
    return all(
        set(ship["coords"]) == ship["hits"]
        for ship in ships.values()
    )


def field_to_bytes():
    # simple flat encoding (adapt if your schiff.py expects something else)
    flat = []
    for row in field:
        for v in row:
            flat.append(v)
    return bytes(flat)


def random_shot():
    return bytes([random.randint(0, 9), random.randint(0, 9)])


# ---------------- HANDSHAKE ----------------

time.sleep(1)

send_frame("STR", b"RL")
recv_frame()  # CSH from host

cs_value = compute_cs(original_field)
send_frame("CSH", cs_value.encode())

# ✅ drain any STR frames before game loop
while True:
    msgid, payload = recv_frame()
    if msgid == "STR":
        pass  # host is signaling they go first
    elif msgid == "BOO":
        # process this first shot directly
        x, y = payload
        if original_field[x][y] != 0:
            result = b'H'
            for sid, ship in ships.items():
                if (x, y) in ship["coords"]:
                    ship["hits"].add((x, y))
                    break
        else:
            result = b'M'
        send_frame("BMR", result)
        send_frame("BOO", random_shot())
        break
    else:
        print("Unexpected during handshake:", msgid)



# ---------------- GAME LOOP ----------------

while True:
    msgid, payload = recv_frame()

    if msgid == "BOO":
        x, y = payload

        # check hit or miss
        if original_field[x][y] != 0:
            result = b'H'

            # ✅ locate the correct ship safely
            for sid, ship in ships.items():
                if (x, y) in ship["coords"]:
                    ship["hits"].add((x, y))
                    break
        else:
            result = b'M'

        # ✅ check end of game FIRST
        
        if all_ships_destroyed():
            print("All ships destroyed -> sending SFR")
            
            for row in range(10):
                row_str = "".join(str(original_field[row][col]) for col in range(10))
                payload = bytes([row]) + row_str.encode('ascii')
                send_frame("SFR", payload)

            break


        # ✅ normal response
        send_frame("BMR", result)

        # ✅ ALWAYS shoot after responding
        send_frame("BOO", random_shot())

    elif msgid == "BMR":
        # ✅ DO NOTHING (pipeline protocol)
        pass

    elif msgid == "SFR":
        print("Host finished game")
        break

    elif msgid == "STR":
        pass  # host signals they go first, just wait for BOO

    else:
        print("Unknown message:", msgid)