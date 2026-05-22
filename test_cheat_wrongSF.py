import sys
import serial
import time
import random
from collections import deque

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
                    ships[ship_id] = {"coords": coords, "hits": set()}
                    ship_id += 1
                    break


place_ships()


def all_ships_destroyed():
    return all(set(ship["coords"]) == ship["hits"] for ship in ships.values())


# ---------------- SFR HELPERS ----------------

def send_sfr_honest():
    """Send our real field."""
    for row in range(10):
        row_str = "".join(str(original_field[row][col]) for col in range(10))
        send_frame("SFR", bytes([row]) + row_str.encode('ascii'))


def send_sfr_forged():
    """Send an all-water field — everything looks like a miss."""
    print("CHEATING: sending forged all-zero SFR")
    for row in range(10):
        send_frame("SFR", bytes([row]) + b'0' * 10)


def recv_and_validate_sfr(we_hit_coords, we_miss_coords):
    """Receive host's 10 SFR rows and validate our shots against their field."""
    their_r = {}
    for _ in range(10):
        msgid, payload = recv_frame()
        if msgid != "SFR":
            print(f"Expected SFR, got {msgid}")
            return
        their_r[payload[0]] = payload[1:].decode('ascii')
    ok = True
    for (x, y) in we_hit_coords:
        if their_r[x][y] == '0':
            print(f"CHEAT DETECTED: we reported HIT at ({x},{y}) but host field shows water!")
            ok = False
    for (x, y) in we_miss_coords:
        if their_r[x][y] != '0':
            print(f"CHEAT DETECTED: we reported MISS at ({x},{y}) but host field shows ship!")
            ok = False
    if ok:
        print("Host field validation passed — no cheating detected.")


def validate_their_shots_on_our_field(hit_coords, miss_coords):
    """Validate host's shots against our own known field."""
    ok = True
    for (x, y) in hit_coords:
        if original_field[x][y] == 0:
            print(f"CHEAT DETECTED: host reported HIT at ({x},{y}) but our field shows water!")
            ok = False
    for (x, y) in miss_coords:
        if original_field[x][y] != 0:
            print(f"CHEAT DETECTED: host reported MISS at ({x},{y}) but our field shows ship!")
            ok = False
    if ok:
        print("Our field validation passed — host shots are consistent.")


# ---------------- WINNING FIRE SOLUTION ----------------

fire_queue = []
fire_index = 0


def build_fire_queue(cs_string):
    queue = []
    for row, ch in enumerate(cs_string):
        if ch != '0':
            for col in range(FIELD_SIZE):
                queue.append((row, col))
    for row, ch in enumerate(cs_string):
        if ch == '0':
            for col in range(FIELD_SIZE):
                queue.append((row, col))
    return queue


def next_shot():
    global fire_index
    if fire_index < len(fire_queue):
        coord = fire_queue[fire_index]
        fire_index += 1
        return bytes([coord[0], coord[1]])
    return bytes([random.randint(0, 9), random.randint(0, 9)])


# ---------------- SHOT TRACKING ----------------

host_hit_coords = []
host_miss_coords = []
we_hit_coords = []
we_miss_coords = []
pending_shots = deque()


# ---------------- HANDSHAKE ----------------

time.sleep(1)

send_frame("STR", b"RL")
_, csh_payload = recv_frame()  # CSH from host
their_cs = csh_payload.decode()

fire_queue = build_fire_queue(their_cs)

cs_value = compute_cs(original_field)
send_frame("CSH", cs_value.encode())

while True:
    msgid, payload = recv_frame()
    if msgid == "STR":
        pass
    elif msgid == "BOO":
        x, y = payload
        if original_field[x][y] != 0:
            result = b'H'
            for sid, ship in ships.items():
                if (x, y) in ship["coords"]:
                    ship["hits"].add((x, y))
                    break
            host_hit_coords.append((x, y))
        else:
            result = b'M'
            host_miss_coords.append((x, y))
        send_frame("BMR", result)
        coord = next_shot()
        pending_shots.append((coord[0], coord[1]))
        send_frame("BOO", coord)
        break
    else:
        print("Unexpected during handshake:", msgid)


# ---------------- GAME LOOP ----------------

while True:
    msgid, payload = recv_frame()

    if msgid == "BOO":
        x, y = payload

        if original_field[x][y] != 0:
            result = b'H'
            for sid, ship in ships.items():
                if (x, y) in ship["coords"]:
                    ship["hits"].add((x, y))
                    break
            host_hit_coords.append((x, y))
        else:
            result = b'M'
            host_miss_coords.append((x, y))

        if all_ships_destroyed():
            print("All our ships destroyed — we lost.")
            validate_their_shots_on_our_field(host_hit_coords, host_miss_coords)
            send_sfr_honest()
            print("Waiting for host SFR to validate our shots...")
            recv_and_validate_sfr(we_hit_coords, we_miss_coords)
            break

        send_frame("BMR", result)
        coord = next_shot()
        pending_shots.append((coord[0], coord[1]))
        send_frame("BOO", coord)

    elif msgid == "BMR":
        if pending_shots:
            c = pending_shots.popleft()
            if payload == b'H':
                we_hit_coords.append(c)
            else:
                we_miss_coords.append(c)

    elif msgid == "SFR":
        # Discard unacknowledged shots — no BMR will come for them
        while pending_shots:
            pending_shots.popleft()

        print("WE WON — receiving host SFR.")
        their_r = {payload[0]: payload[1:].decode('ascii')}
        for _ in range(9):
            m, p = recv_frame()
            if m == "SFR":
                their_r[p[0]] = p[1:].decode('ascii')

        # Validate host's field against our shots honestly
        ok = True
        for (x, y) in we_hit_coords:
            if their_r[x][y] == '0':
                print(f"CHEAT DETECTED: we reported HIT at ({x},{y}) but host field shows water!")
                ok = False
        for (x, y) in we_miss_coords:
            if their_r[x][y] != '0':
                print(f"CHEAT DETECTED: we reported MISS at ({x},{y}) but host field shows ship!")
                ok = False
        if ok:
            print("Host field validation passed — no cheating detected.")
        validate_their_shots_on_our_field(host_hit_coords, host_miss_coords)

        # CHEAT: send forged all-zero SFR instead of real field
        send_sfr_forged()
        break

    elif msgid == "STR":
        pass

    else:
        print("Unknown message:", msgid)