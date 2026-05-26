#!/usr/bin/env python3 
# vim: set ts=4 sw=4 et:

#
#   MCI ES - exercise 3 - reference solution
#   Roland Lezuo <roland.lezuo@embedded-solutions.at> (c) 2024
#

import typing
import argparse
import logging
import serial
import random
import time
import enum
import re
import traceback

# field configuration: key ... ship length, value ... nr. of such ships
nr_ships = {
    5: 1,
    4: 2,
    3: 3,
    2: 4,
}

# some constants
FIELD_SZ = 10

# protocol message IDs (3-byte ASCII identifiers)
MSG_START = b'STR' # STR ... start, payload is opponent name as ASCII string, e.g. "RL" for Roland Lezuo
MSG_CS = b'CSH' # CS ... checksum, a string of 10 digits, each digit is the number of ship parts in the corresponding row
MSG_SF = b'SFR' # SF ... ship field, payload is 11 bytes, first byte is row index, followed by 10 ASCII digits representing the row data, e.g. "0000200000" for a row with a single ship part in column 4
MSG_BOOM = b'BOO' # BOO ... boom, payload is 2 bytes, row and column to fire at, e.g. b'\x03\x04' for firing at row 3 column 4
MSG_BOOM_RESULT = b'BMR' # BMR ... boom result, payload is 1 byte, b'H' for hit, b'M' for miss, e.g. b'H' for a hit at the coordinates we fired at with BOO

class SerialIO:
    """handling communication over the serial port using framed messages.

    Message frame: [Header][Message-ID][Länge][Payload][CRC][EOF]
    Header: `#`
    Message-ID: 3 bytes
    Länge: 1 byte
    Payload: `Länge` bytes
    CRC: CRC-8 (polynomial 0x07, init 0x00, no reflection, no final XOR — CRC-8/SMBUS)
         computed over Message-ID, Länge and Payload
    EOF: `$`
    """
    HEADER_BYTE = b'#'
    EOF_BYTE = b'$'

    # CRC-8 lookup table, polynomial 0x07 (CRC-8/SMBUS)
    _CRC8_TABLE = [0] * 256

    @classmethod
    def _build_crc8_table(cls):
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x07
                else:
                    crc <<= 1
            cls._CRC8_TABLE[i] = crc & 0xFF

    def __init__(self, args):
        self._build_crc8_table()
        self.ser_dev = args.ser_dev
        self.notimeout = args.notimeout
        self.raw_debug = getattr(args, 'raw_debug', False)
        self.dev = serial.serial_for_url(self.ser_dev, 9600, timeout=2)

    def _calc_crc(self, msg_id: bytes, length: int, payload: bytes) -> int:
        """CRC-8/SMBUS: polynomial 0x07, init 0x00, no reflection, no final XOR.
        Matches the STM32F091 hardware CRC peripheral configured with an 8-bit polynomial 0x07.
        Reference check value: crc8(b'\\x31'..b'\\x39') == 0xF4
        """
        data = msg_id + bytes([length]) + payload
        crc = 0x00
        for byte in data:
            crc = self._CRC8_TABLE[crc ^ byte]
        return crc

    def _read_exact(self, count: int) -> bytes:
        data = b''
        while len(data) < count:
            if self.raw_debug:
                logging.debug("SERIAL RX waiting for %d bytes", count - len(data))
            chunk = self.dev.read(count - len(data))
            if chunk == b'':
                if self.notimeout:
                    continue
                raise TimeoutError('timeout while waiting for data from device')
            if self.raw_debug:
                logging.debug("SERIAL RX %s", chunk.hex())
            data += chunk
        return data

    def send_message(self, msg_id: bytes, payload: bytes):
        if payload is None:
            payload = b''
        if not isinstance(msg_id, (bytes, bytearray)) or len(msg_id) != 3:
            raise ValueError('message ID must be 3 ASCII bytes')
        if len(payload) > 255:
            raise ValueError('payload too long for protocol frame')
        frame = self.HEADER_BYTE + msg_id + bytes([len(payload)]) + payload
        crc = self._calc_crc(msg_id, len(payload), payload)
        frame += bytes([crc]) + self.EOF_BYTE
        logging.debug("--> %s", frame.hex())
        if self.raw_debug:
            logging.debug("SERIAL TX %s", frame.hex())
        self.dev.write(frame)

    def receive_message(self) -> tuple[bytes, bytes]:
        while True:
            c = self.dev.read(1)
            if c == b'':
                if self.notimeout:
                    continue
                raise TimeoutError('timeout while waiting for data from device')
            if c != self.HEADER_BYTE:
                continue
            break

        header = self._read_exact(4)
        msg_id, length = header[:3], header[3]
        payload = self._read_exact(length)
        crc_byte = self._read_exact(1)[0]
        eof = self._read_exact(1)
        if eof != self.EOF_BYTE:
            raise RuntimeError('protocol error: missing EOF')
        expected_crc = self._calc_crc(msg_id, length, payload)
        if crc_byte != expected_crc:
            raise RuntimeError('protocol error: CRC mismatch')

        logging.debug("<-- id=%s len=%d payload=%s crc=%02x", msg_id.decode('ascii', errors='ignore'), length, payload, crc_byte)
        return msg_id, payload

class Field:
    """our game field

    will generate a truely random field for each game
    detects the "we lose" condition
    generates pre-formatted F and R records
    """
    def __init__(self, sz=FIELD_SZ):
        self.MAX_RETRIES = 1000
        generated = False
        while not generated:
            logging.debug("generating field")
            generated = self.generate_field(sz)

    def generate_field(self, sz):
        debug_placement = False
        while True:
            retry_counter = 0
            self.f = dict()
            self.sz = FIELD_SZ
            for x in range(0, self.sz):
                for y in range(0, self.sz):
                    self.f[self.xy_to_idx(x, y)] = 0

            for k,v in nr_ships.items():
                for _ in range(0, v):
                    in_conflict = True
                    while in_conflict:
                        d = random.choice(['vert', 'horiz'])

                        if d == 'vert':
                            x = random.randint(0, sz-k-1)
                            y = random.randint(0, sz-1)
                        else:
                            x = random.randint(0, sz-1)
                            y = random.randint(0, sz-k-1)

                        if debug_placement: logging.debug("trying to place a ship of length {} in {} direction at {},{}".format(k, d, x, y))
                        in_conflict = any(map(lambda xy: self.f[self.xy_to_idx(xy[0],xy[1])] != 0, self.surr_fields(x, y, d, k)))
                        if in_conflict:
                            if debug_placement: logging.debug("placing ship of length {} in {} direction at {},{} failed".format(k, d, x, y))
                            retry_counter += 1
                            if retry_counter >= self.MAX_RETRIES:
                                return False
                        else:
                            if debug_placement: logging.debug("placed a ship if length {} at {},{}".format(k, x, y))
                            if d == 'vert':
                                for kd in range(0, k):
                                    self.f[self.xy_to_idx(x+kd, y)] = k
                            else:
                                for kh in range(0, k):
                                    self.f[self.xy_to_idx(x, y+kh)] = k

            self.sf_records = []
            for x in range(0, self.sz):
                f = ""
                for y in range(0, self.sz):
                    f += "{}".format(self.f[self.xy_to_idx(x, y)])
                self.sf_records.append(f)

            return True

    def xy_to_idx(self, x, y):
        return x*self.sz+y

    def shot_at(self, x, y):
        if self.f[self.xy_to_idx(x,y)] in [0, 'W']:
            self.f[self.xy_to_idx(x,y)] = 'W'
            return False
        else:
            self.f[self.xy_to_idx(x,y)] = 'T'
            return True

    def ships_left(self):
        return sum(map(lambda x: 0 if x in [0, 'W', 'T'] else 1, self.f.values()))

    def __str__(self):
        s = "Field:\n"
        for x in range(0, self.sz):
            s += "    "
            for y in range(0, self.sz):
                s += "{}".format(self.f[self.xy_to_idx(x,y)])
            s += '\n'
        return s

    def get_cs_record(self):
        r ="" 
        for x in range(0, self.sz):
            r += "{}".format(sum(map(lambda y: self.f[self.xy_to_idx(x,y)] != 0, range(0, self.sz))))
        return r

    def get_sf_records(self):
        return self.sf_records

    def surr_fields(self, x, y, d, k):
        s = []
        if d == 'vert':
            for yy in [y-1, y, y+1]:
                if yy < 0: continue
                if yy >= self.sz: continue
                for xx in range(x-1, x+k+1):
                    if xx < 0: continue
                    if xx >= self.sz: continue
                    s.append( (xx, yy) )
        else:
             for xx in [x-1, x, x+1]:
                if xx < 0: continue
                if xx >= self.sz: continue
                for yy in range(y-1, y+k+1):
                    if yy < 0: continue
                    if yy >= self.sz: continue
                    s.append( (xx, yy) )
        return s

class FireSolution:
    def __init__(self, their_cs, sz=FIELD_SZ):
        self.their_cs = their_cs
        self.sz = sz
        self.cand = [(x,y) for x in range(0, sz) for y in range(0, sz)]
        self.hit_list = []
        self.miss_list = []

    def get_coord(self) -> tuple[int, int]:
        assert(False)

    def update(self, coord, was_a_hit):
        if was_a_hit:
            self.hit_list.append(coord)
        else:
            self.miss_list.append(coord)

    def validate(self, their_r):
        no_error = True
        for r,c in self.hit_list:
            if their_r[r][c] == '0':
                logging.error("we shot at row={} col={} and hit, but according to your SF records there is water".format(r, c))
                no_error = False
        logging.info("I've checked all your {} number of hits reported, they all are correct according to your SF record".format(len(self.hit_list)))
        for r,c in self.miss_list:
            if their_r[r][c] != '0':
                logging.error(f"Checking cell: their_r[{r}][{c}] = {their_r[r][c]}")
                logging.error("we shot at row={} col={} and missed, but accordingly to your SF records there is a ship".format(r, c))
                no_error = False
        logging.info("I've checked all your {} number of misses reported, they all are correct according to your SF record".format(len(self.miss_list)))
        return no_error

class StupidFireSolution(FireSolution):
    def get_coord(self) -> tuple[int, int]:
        if len(self.cand) == 0:
            raise IndexError('no more fire coords, the enemy MUST be dead already, liar!')
        return self.cand.pop(random.randint(0, len(self.cand)-1))

class StateMachine:
    class State(enum.Enum):
        INIT = 1
        PLAY = 3
        FINISHED = 4

    def __init__(self, ser_io):
        self.state = self.State.INIT
        self.ser_io = ser_io
        self.we_won = False
        self.hit_counter = 0

    def set_fire_solution(self, fs):
        self.fs = fs

    def is_finished(self):
        return self.state == self.State.FINISHED

    def reset(self):
        self.state = self.State.INIT

    def timeout(self):
        logging.error("device did not answer in time, is it connected?")
        self.state = self.State.FINISHED

    def err_out(self):
        logging.error("protocol mismatch, surely your code is to blame ;)")
        self.state = self.State.FINISHED

    def start(self, our_field):
        if self.state != self.State.INIT:
            raise RuntimeError("StateMachine start() when not in INIT")
        self.f = our_field
        self.hit_counter = 0
        while True:
            self.ser_io.send_message(MSG_START, b'')
            try:
                msg_id, payload = self.ser_io.receive_message()
                if self.start_handler(msg_id, payload):
                    break
            except TimeoutError:
                logging.debug("no reply to START frame, retrying...")
                pass

    def start_handler(self, msg_id: bytes, payload: bytes) -> bool:
        if msg_id != MSG_START:
            raise RuntimeError("expected START message, got something else")
        self.opponent = payload.decode('ascii', errors='ignore')
        logging.info("Opponent name {}".format(self.opponent))
        self.ser_io.send_message(MSG_CS, self.f.get_cs_record().encode('ascii'))
        msg_id, payload = self.ser_io.receive_message()
        return self.cs_handler(msg_id, payload)

    def cs_handler(self, msg_id: bytes, payload: bytes) -> bool:
        if msg_id != MSG_CS:
            raise RuntimeError("expected CS message, got something else")
        self.their_cs = payload.decode('ascii')
        logging.debug("Received opponent CS: {}".format(self.their_cs))
        their_ships_total = sum(map(lambda x: int(x), self.their_cs))
        our_ships_total = sum(map(lambda x: x*nr_ships[x], nr_ships.keys()))
        if our_ships_total != their_ships_total:
            raise RuntimeError("total number of reported ship parts {}, but it should be {}".format(their_ships_total, our_ships_total))
        self.state = self.State.PLAY
        return True

    def sf_handler(self, msg_id: bytes, payload: bytes) -> bool:
        if msg_id != MSG_SF:
            return False
        if len(payload) != 11:
            raise RuntimeError('SF message payload must be 11 bytes')
        row = payload[0]
        row_data = payload[1:].decode('ascii')
        self.their_r[row] = row_data
        return True

    def validate_their_r(self):
        if len(self.their_r) != self.f.sz:
            raise RuntimeError("expected {} SF records, only have {}".format(self.f.sz, len(self.their_r)))
        for i in range(0, self.f.sz):
            if not i in self.their_r:
                raise RuntimeError("expected key {} in SF records, it is not".format(i))
        actual_cs = ""
        for i in range(0, self.f.sz):
            actual_cs += "{}".format(sum(map(lambda x: x != '0', self.their_r[i])))
        if actual_cs != self.their_cs:
            logging.error("Your CS is {} but you initally announced: {}".format(actual_cs, self.their_cs))
        logging.info("Their SF:")
        for i in range(0, len(self.their_r)):
            logging.info("{}".format(self.their_r[i]))
        vv = dict()
        for i in range(0, len(self.their_r)):
            for j in range(0, len(self.their_r[i])):
                val = self.their_r[i][j]
                if isinstance(val, int):
                    val = chr(val)
                vv[self.f.xy_to_idx(i, j)] = val
        detected_ships = {}
        has_error = False
        for i in range(0, len(self.their_r)):
            for j in range(0, len(self.their_r[i])):
                cell = vv[self.f.xy_to_idx(i, j)]
                if cell == '0':
                    continue
                if (i > 0 and vv[self.f.xy_to_idx(i-1, j)] == cell) or \
                   (j > 0 and vv[self.f.xy_to_idx(i, j-1)] == cell):
                    continue
                ship_len = cell
                if cell not in ['2', '3', '4', '5']:
                    logging.error(f"invalid ship value '{ship_len}' at ({i},{j})")
                    has_error = True
                    continue
                ship_len = int(cell)
                if not ship_len in detected_ships:
                    detected_ships[ship_len] = 1
                else:
                    detected_ships[ship_len] += 1
                ship_h = False
                ship_v = False
                if j+ship_len-1 < self.f.sz and vv[self.f.xy_to_idx(i, j+1)] == str(ship_len):
                    ship_h = all(map(lambda x: vv[self.f.xy_to_idx(i, j+x)] == vv[self.f.xy_to_idx(i, j)], range(0, ship_len)))
                elif (i + ship_len - 1 < self.f.sz and vv[self.f.xy_to_idx(i+1, j)] == str(ship_len)):
                    ship_v = all(map(lambda x: vv[self.f.xy_to_idx(i+x,j)] == vv[self.f.xy_to_idx(i, j)], range(0, ship_len)))
                else:
                    logging.error("your ship of len={}, starting at row {} col {} overlaps the gamefield".format(ship_len, i, j))
                    has_error = True
                if not ship_h and not ship_v:
                    logging.error("your ship of len={}, starting at row {} col {} is neither horizontally nor vertically straight".format(ship_len, i, j))
                    has_error = True
                if ship_h:
                    for x in range(0, ship_len):
                        vv[self.f.xy_to_idx(i, j+x)] = '0'
                else:
                    for x in range(0, ship_len):
                        vv[self.f.xy_to_idx(i+x, j)] = '0'
                if any(map(lambda xy: vv[self.f.xy_to_idx(xy[0],xy[1])] != '0', self.f.surr_fields(i, j, 'vert' if ship_v else 'horiz', ship_len))):
                    logging.error("your ship of len={}, starting at row {} col {} is not only surrounded by water".format(ship_len, i, j))
                    has_error = True
                logging.info("I've just check your ship of len={} starting at row {} col {} ({} placement), if no errors are shown it was good".format(ship_len, i, j, 'vert ' if ship_v else 'horiz'))
        for k in nr_ships.keys():
            try:
                if detected_ships[k] != nr_ships[k]:
                    logging.error("number of ships with len={} not correct!".format(k))
                    has_error = True
            except:
                logging.error("do you miss ships of certain length at all?")
                has_error = True
        if not self.fs.validate(self.their_r):
            has_error = True
        if has_error:
            raise RuntimeError("did you try to cheat?")

    def boom_handler(self, msg_id: bytes, payload: bytes) -> tuple[bool, bool, bool]:
        if msg_id == MSG_BOOM_RESULT:
            if len(payload) != 1:
                raise RuntimeError('BOOM result payload wrong size')
            we_hit = payload == b'H'
            return True, False, we_hit
        if msg_id == MSG_SF:
            self.their_r = {}
            row = payload[0]
            cols = payload[1:]
            if len(cols) != 10:
                raise RuntimeError('invalid SF row length')
            self.their_r[row] = cols.decode('ascii')
            for _ in range(9):
                msg_id, payload = self.ser_io.receive_message()
                if msg_id != MSG_SF:
                    raise RuntimeError('expected SF message after win')
                row = payload[0]
                cols = payload[1:]
                if len(cols) != 10:
                    raise RuntimeError('invalid SF row length')
                self.their_r[row] = cols.decode('ascii')
            self.validate_their_r()
            return True, True, False
        raise RuntimeError('expected BOOM result or SF message, got something else')

    def hitmiss_handler(self, msg_id: bytes, payload: bytes) -> tuple[bool, tuple[int, int]]:
        if msg_id != MSG_BOOM or len(payload) != 2:
            raise RuntimeError('expected BOOM coordinate message, got something else')
        coords = int(payload[0]), int(payload[1])
        return True, coords

    def play(self):
        xy = self.fs.get_coord()
        self.ser_io.send_message(MSG_BOOM, bytes([xy[0], xy[1]]))
        msg_id, payload = self.ser_io.receive_message()
        ok, we_won, we_hit = self.boom_handler(msg_id, payload)
        if not ok:
            self.err_out()
            return
        send_sf_records = False
        they_hit = False
        if not we_won:
            self.fs.update(xy, we_hit)
            if we_hit:
                logging.info("we HIT  @{}".format(xy))
                self.hit_counter += 1
                max_hits = sum(map(lambda x: x[0]*x[1], nr_ships.items()))
                if self.hit_counter >= max_hits:
                    raise RuntimeError("According to you we've hit more than {} times, but you never sent the SF records".format(max_hits))
            else:
                logging.info("we MISS @{}".format(xy))
            msg_id, payload = self.ser_io.receive_message()
            ok, xy = self.hitmiss_handler(msg_id, payload)
            if not ok:
                self.err_out()
                return
            they_hit = self.f.shot_at(*xy)
            if they_hit:
                logging.info("they HIT  @{}".format(xy))
            else:
                logging.info("they MISS @{}".format(xy))
            logging.info("Our Gamefield\n: {}".format(self.f))
        else:
            send_sf_records = True
        we_lost = False
        if self.f.ships_left() == 0:
            logging.info("we have no ships left, we just lost the game")
            send_sf_records = True
            we_lost = True
        if send_sf_records:
            for row_idx, row in enumerate(self.f.get_sf_records()):
                payload = bytes([row_idx]) + row.encode('ascii')
                self.ser_io.send_message(MSG_SF, payload)
        else:
            result_payload = b'H' if they_hit else b'M'
            self.ser_io.send_message(MSG_BOOM_RESULT, result_payload)
        if we_lost or we_won:
            self.their_r = {}
            for _ in range(0, self.f.sz):
                msg_id, payload = self.ser_io.receive_message()
                if not self.sf_handler(msg_id, payload):
                    raise RuntimeError('expected SF message after game end')
            self.validate_their_r()
            self.state = self.State.FINISHED
            self.we_won = we_won


def main(state_machine, args):
    logging.info("Starting protocol on {}".format(state_machine.ser_io.ser_dev))
    cnt = 0
    aborted = 0
    won = 0
    lost = 0
    if args.tournament:
        print("0--------1---------2---------3---------4---------5---------6---------7---------8---------9---------|")
    while True:
        tournament_result_char = 'a'
        try:
            state_machine.reset()
            our_field = Field()
            logging.info("Our Gamefield\n: {}".format(our_field))
            state_machine.start(our_field)
            fire_solution = StupidFireSolution(state_machine.their_cs)
            state_machine.set_fire_solution(fire_solution)
            while not state_machine.is_finished():
                state_machine.play()
            if state_machine.we_won:
                won += 1
                tournament_result_char = 'w'
            else:
                lost += 1
                tournament_result_char = 'l'
        except (TimeoutError, RuntimeError) as e:
            cheat_error = "cheat" in str(e).lower() or "never sent the sf" in str(e).lower()
            if cheat_error:
                logging.error("Cheating detected — stopping: {}".format(e))
                raise
            if not args.tournament:
                logging.error("Exception in game-loop, will reset the game state")
                logging.error(e)
                traceback.print_exc()
            aborted += 1
        if args.single:
            return
        cnt += 1
        if args.tournament and cnt >= 100:
            print("")
            print("TOURNAMENT RESULT: played {} (we won/we lost/aborted): {} {} {}".format(cnt, won, lost, aborted))
            return
        if not args.tournament:
            logging.debug("waiting 1 second")
            time.sleep(1)
        else:
            print(tournament_result_char, end="", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(epilog="Ein Schiff im Hafen ist sicher, doch dafür werden Schiffe nicht gebaut")
    parser.add_argument('ser_dev', help="serial device, e.g. /dev/ttyUSB0 with Linux, COM23 with Windows")
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-s', '--single', action='store_true')
    parser.add_argument('-n', '--notimeout', action='store_true')
    parser.add_argument('-t', '--tournament', action='store_true')
    parser.add_argument('--raw-debug', action='store_true', help='log raw serial bytes sent and received')
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif args.tournament:
        logging.basicConfig(level=logging.WARN)
    else:
        logging.basicConfig(level=logging.INFO)
    if args.raw_debug:
        logging.getLogger().setLevel(logging.DEBUG)
    ser_io = SerialIO(args)
    sm = StateMachine(ser_io)
    main(sm, args)
