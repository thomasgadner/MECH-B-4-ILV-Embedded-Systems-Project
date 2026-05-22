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


def random_shot():
    return bytes([random.randint(0, 9), random.randint(0, 9)])


def send_sfr():
    """Send our own field row by row."""
    for row in range(10):
        row_str = "".join(str(original_field[row][col]) for col in range(10))
        payload = bytes([row]) + row_str.encode('ascii')
        send_frame("SFR", payload)


def recv_and_validate_sfr(we_hit_coords, we_miss_coords):
    """Receive 10 SFR rows from host and validate OUR shots against their field."""
    their_r = {}
    for _ in range(10):
        msgid, payload = recv_frame()
        if msgid != "SFR":
            print(f"Expected SFR, got {msgid}")
            return
        row = payload[0]
        s = payload[1:].decode('ascii')
        their_r[row] = s
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
    """Validate host's shots against our own known field — no SFR exchange needed."""
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


# track host's shots on us (to validate against our own field)
host_hit_coords = []   # coords where host hit us
host_miss_coords = []  # coords where host missed us

# track our shots at the host (to validate against host's SFR)
we_hit_coords = []
we_miss_coords = []

# FIFO queue of coords we fired — each BMR pops the oldest entry
from collections import deque
shot_queue = deque()

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
            host_hit_coords.append((x, y))
        else:
            result = b'M'
            host_miss_coords.append((x, y))
        send_frame("BMR", result)
        shot = random_shot()
        shot_queue.append((shot[0], shot[1]))
        send_frame("BOO", shot)
        break
    else:
        print("Unexpected during handshake:", msgid)



# ---------------- GAME LOOP ----------------

while True:
    msgid, payload = recv_frame()

    if msgid == "BOO":
        x, y = payload

        # check hit or miss on our field
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

        # check end of game FIRST
        if all_ships_destroyed():
            # We LOST: validate host's shots against our own field locally,
            # send our SFR, then receive and validate host's SFR against our shots.
            print("All our ships destroyed — we lost.")
            validate_their_shots_on_our_field(host_hit_coords, host_miss_coords)
            send_sfr()
            print("Waiting for host SFR to validate our shots...")
            recv_and_validate_sfr(we_hit_coords, we_miss_coords)
            break

        # normal response
        send_frame("BMR", result)
        shot = random_shot()
        shot_queue.append((shot[0], shot[1]))
        send_frame("BOO", shot)

    elif msgid == "BMR":
        # Pop the oldest shot we fired and record the result
        if shot_queue:
            coord = shot_queue.popleft()
            if payload == b'H':
                we_hit_coords.append(coord)
            else:
                we_miss_coords.append(coord)

    elif msgid == "SFR":
        # Discard any shots fired after the host already decided to send SFR —
        # we never got a BMR for them so we don't know the result; skip them.
        while shot_queue:
            shot_queue.popleft()

        # We WON: receive remaining SFR rows (first row already in payload),
        # validate host's field against our shots, then send our SFR back.
        print("Host finished game — we won! Receiving host SFR.")
        def parse_sfr_payload(p):
            row = p[0]
            row_data = p[1:].decode('ascii')
            return row, row_data

        row, row_data = parse_sfr_payload(payload)
        their_r = {row: row_data}
        for _ in range(9):
            m, p = recv_frame()
            if m == "SFR":
                row, row_data = parse_sfr_payload(p)
                their_r[row] = row_data

        print(f"DEBUG: we_hit={we_hit_coords}")
        print(f"DEBUG: we_miss={we_miss_coords}")
        print("Host field:")
        for r in range(10):
            print(f"  row {r}: {their_r.get(r, '???')}")

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
        print("Sending our SFR so host can validate us.")
        send_sfr()
        break

    elif msgid == "STR":
        pass  # host signals they go first, just wait for BOO

    else:
        print("Unknown message:", msgid)