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

# some constatns
FIELD_SZ = 10

class SerialIO:
    """ handling communication over the serial port

    provides convenience function like receiving and sending lines and implements timeout
    """
    def __init__(self, args):
        self.ser_dev = args.ser_dev
        self.notimeout = args.notimeout
        self.dev = serial.serial_for_url(self.ser_dev, 115200, timeout=2)

    def send_line(self, text):
        logging.debug("-->{}".format(text))
        self.dev.write("{}\r\n".format(text).encode('ascii'))

    def receive(self, callback):
        l = ""
        while True:
            c = self.dev.read(1)
            if c == b"":
                if self.notimeout:
                    continue
                else:
                    raise TimeoutError('timeout while waiting for data from device')
            if c == b"\r":
                continue
            if c == b"\n":
                if l.startswith("DH_#"):
                    # this is a comment line, just print it
                    print("COMMENT: {}".format(l))
                    l = ""
                    continue
                else:
                    break
            l += c.decode('ascii')
        logging.debug("<--{}".format(l))
        return callback(l, False)

class Field:
    """our game field

    will generate a truely random field for each game
    detects the "we lose" condition
    generates pre-formatted F and R records
    """
    def __init__(self, sz=FIELD_SZ):
        # the placing algoithm may get stuck because ships may be placed in a way preventing all shipds from beeing placed
        # we thus try a few iterations and give up eventually starting from scratch
        # one could be more clever here, e.g. implementing a backtracking solution
        self.MAX_RETRIES = 1000
        generated = False
        while not generated:
            logging.debug("generating field")
            generated = self.generate_field(sz)

    # returns True when all ships have been placed, False if had to give up
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
                                # evntually bail out
                                return False
                        else:
                            if debug_placement: logging.debug("placed a ship if length {} at {},{}".format(k, x, y))
                            if d == 'vert':
                                for kd in range(0, k):
                                    self.f[self.xy_to_idx(x+kd, y)] = k
                            else:
                                for kh in range(0, k):
                                    self.f[self.xy_to_idx(x, y+kh)] = k

            # pre-calcuate the sf-records (we do not cheat)
            self.sf_records = []
            for x in range(0, self.sz):
                f = "SF{}D".format(x)
                for y in range(0, self.sz):
                    f += "{}".format(self.f[self.xy_to_idx(x, y)])
                self.sf_records.append(f)

            # all ships have been placed
            return True

    # x ... horizontal, y ... vertical direction
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

    # returns index of all surrounding fields on map for ship of length k in direction d starting at x,y
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
    """a base class for all Fire Solutions, this calculates where we shoot next

    defines get_coord / upate interface and generates a list of all candidates
    must be overloaded as get_coord asserts
    """
    def __init__(self, their_cs, sz=FIELD_SZ):
        self.their_cs = their_cs
        self.sz = sz
        # all candiate coordiantes to shoot at
        self.cand = [(x,y) for x in range(0, sz) for y in range(0, sz)]
        self.hit_list = []
        self.miss_list = []

    def get_coord(self) -> tuple[int, int]:
        """get next coordinates to fire at
        Returns:
            ((int,int)): tuple of row column to fire at, may raise if no more possibilities to fire at
        """
        # overload me and implement me!
        assert(False)

    def update(self, coord, was_a_hit):
        """keep record for later ;)
        Args:
            coord ((int,int)): tuple of row column where we fired
            was_a_hit (bool): whether we hit there or not
        Returns:
            None
        """
        if was_a_hit:
            self.hit_list.append(coord)
        else:
            self.miss_list.append(coord)

    def validate(self, their_r):
        """later is now, test our hit/miss lists against the actual gamefield
        Args:
            their_r, SF record (data onyl) as string
        Returns:
            None
        """
        no_error = True
        for r,c in self.hit_list:
            if their_r[r][c] == '0':
                logging.error("we shot at row={} col={} and hit, but according to your SF records there is water".format(r, c))
                no_error = False
        logging.info("I've checked all your {} number of hits reported, they all are correct according to your SF record".format(len(self.hit_list)))
        for r,c in self.miss_list:
            if their_r[r][c] != '0':
                logging.error("we shit at row={} col={} and missed, but accordingly to your SF records there is a ship".format(r, c))
                no_error = False
        logging.info("I've checked all your {} number of misses reported, they all are correct according to your SF record".format(len(self.miss_list)))
        
        return no_error
    

class StupidFireSolution(FireSolution):
    """a very basic fire solution, a truly random player

    should be slightly better than just stupid, is a good baseline for a tournament
    """
    def get_coord(self) -> tuple[int, int]:
        if len(self.cand) == 0:
            raise IndexError('no more fire coords, the enemy MUST be dead already, liar!')
        # pick a random candiate (and remove form candidate list)
        return self.cand.pop(random.randint(0, len(self.cand)-1))

class StateMachine:
    """ a state machine implementing the game protocol
    """
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
            self.ser_io.send_line("HD_START")
            try:
                ok = self.ser_io.receive(self.start_handler)
                if ok: break 
            except TimeoutError as _:
                # when we send out starts and wait for a device timeouts are not fatal, just continue
                pass

    def start_handler(self, text, was_timeout):
        if was_timeout:
            self.timeout()
            return False
        else:
            m = re.match(r"^DH_START_(.+)$", text)
            if m is None:
                raise RuntimeError("expected DH_START_ message, got something else")
            self.opponent = m[1]
            logging.info("Opponent name {}".format(self.opponent))

            # send our checksum
            self.ser_io.send_line("HD_CS_{}".format(self.f.get_cs_record()))
            # receive opponent's checksum
            if not self.ser_io.receive(self.cs_handler):
                raise RuntimeError("error while processing opponent's CS message")

            self.state = self.State.PLAY
            return True

    def cs_handler(self, text, was_timeout):
        if was_timeout:
            self.timeout()
            return False

        m = re.match(r"^DH_CS_(\d{10})$", text)
        if m is None:
                raise RuntimeError("expected DH_CS_ message, got something else")
        self.their_cs = m[1]
        logging.debug("Received opponent CS: {}".format(self.their_cs))
        their_ships_total = sum(map(lambda x: int(x), self.their_cs))
        our_ships_total = sum(map(lambda x: x*nr_ships[x], nr_ships.keys()))

        if our_ships_total != their_ships_total:
            raise RuntimeError("total number of reported ship parts {}, but it should be {}".format(their_ships_total, our_ships_total))
        return True

    def sf_handler(self, text, was_timeout) -> bool:
        if was_timeout:
            self.timeout()
            return False

        m = re.match(r"^DH_SF(\d)D(\d{10})$", text)
        if m is None:
             return False

        self.their_r[int(m[1])] = m[2]
        return True

    def validate_their_r(self):
        """ validates that we completly received their SF records """
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

        # now validate their SF, i.e. correct number of ships, correct placement and the like
        # we scan the field top-down, left-right and find the orientation of each one
        vv = dict()

        for i in range(0, len(self.their_r)):
            for j in range(0, len(self.their_r[i])):
                vv[self.f.xy_to_idx(i, j)] = self.their_r[i][j]

        detected_ships = {}
        has_error = False
        for i in range(0, len(self.their_r)):
            for j in range(0, len(self.their_r[i])):
                if vv[self.f.xy_to_idx(i, j)] != '0':
                    # we found something, count it
                    ship_len = vv[self.f.xy_to_idx(i, j)]
                    assert(ship_len in ['2', '3', '4', '5'])
                    ship_len = int(ship_len)
                    if not ship_len in detected_ships:
                        detected_ships[ship_len] = 1
                    else:
                        detected_ships[ship_len] += 1

                    ship_h = False
                    ship_v = False
                    if j+ship_len-1 < self.f.sz and vv[self.f.xy_to_idx(i, j+1)] == str(ship_len):
                        # we may look to the right, we may have a horizontal ship after all
                        ship_h = all(map(lambda x: vv[self.f.xy_to_idx(i, j+x)] == vv[self.f.xy_to_idx(i, j)], range(0, ship_len)))
                    elif i+ship_len-1 < self.f.sz and self.their_r[i+1][j] == str(ship_len):
                        # we may look downwards, we may have a vertical ship after all
                        ship_v = all(map(lambda x: vv[self.f.xy_to_idx(i+x,j)] == vv[self.f.xy_to_idx(i, j)], range(0, ship_len)))
                    else:
                        logging.error("your ship of len={}, starting at row {} col {} overlaps the gamefield".format(ship_len, i, j))
                        has_error = True

                    
                    # is the ship staight?
                    if not ship_h and not ship_v:
                        logging.error("your ship of len={}, starting at row {} col {} is neither horizontally nor vertically straight".format(ship_len, i, j))
                        has_error = True


                    # ship seems to be fine, now delete it otherwise we will later find a middle part and fail miserably
                    if ship_h:
                        for x in range(0, ship_len): 
                            vv[self.f.xy_to_idx(i, j+x)] = '0'
                    else:
                        for x in range(0, ship_len): 
                            vv[self.f.xy_to_idx(i+x, j)] = '0'

                    if False:
                        for x in range(0, 10):
                            l = ""
                            for y in range(0, 10):
                               l += vv[self.f.xy_to_idx(x,y)] 
                            logging.info("{}".format(l))

                    # are the surround fields empty, need to do that AFTER we cleared the ship: the field occupied by the ship are part of surr_fields as well
                    if any(map(lambda xy: vv[self.f.xy_to_idx(xy[0],xy[1])] != '0', self.f.surr_fields(i, j, 'vert' if ship_v else 'horiz', ship_len))):
                        logging.error("your ship of len={}, starting at row {} col {} is not only surrounded by water".format(ship_len, i, j))
                        has_error = True

                    logging.info("I've just check your ship of len={} starting at row {} col {} ({} placement), if no errors are shown it was good".format(ship_len, i, j, 'vert ' if ship_v else 'horiz'))

        # now check if all ship have been found
        for k in nr_ships.keys():
            try:
                if detected_ships[k] != nr_ships[k]:
                    logging.error("number of ships with len={} not correct!".format(k))
                    has_error = True
            except:
                logging.error("do you miss ships of certain length at all?")
                has_error = True

        # now check if they ever lied to us during the game
        if not self.fs.validate(self.their_r):
            has_error = True

        if has_error: 
            raise RuntimeError("did you try to cheat?")
       
    def boom_handler(self, text, was_timeout) -> tuple[bool, bool, bool]:
        if was_timeout:
            self.timeout()
            return False, False, False

        m = re.match(r"^DH_BOOM_([HM])$", text)
        if m is None:
            # maybe we won, try to parse text as sf record
            self.their_r = {}
            ok = self.sf_handler(text, False)
            if not ok:
                raise RuntimeError("expected DH_BOOM_H or DH_BOOM_M or DH_SF message(s), got something else")
            else:
                for _ in range(1, self.f.sz):
                    # read more of those messaged, one has already been received
                    self.ser_io.receive(self.sf_handler)

                # raises if data is not correct
                self.validate_their_r()


            # sucess, we won and we hit ;)
            return True, True, True
        else:
            if m[1] == 'H':
                we_hit = True
            else:
                we_hit = False
            return True, False, we_hit

    def hitmiss_handler(self, text, was_timeout) -> tuple[bool, tuple[int, int] | None]:
        if was_timeout:
            self.timeout()
            return False, None 

        m = re.match(r"^DH_BOOM_(\d)_(\d)$", text)
        if m is None:
                raise RuntimeError("expected DH_BOOM_x_y message, got something else")
        coords = int(m[1]),int(m[2])
        return True, coords

    def play(self):
        # we shoot, first get some coordinates tuple[int,int], may raise exception
        xy = self.fs.get_coord()

        self.ser_io.send_line("HD_BOOM_{}_{}".format(*xy))
        ok,we_won,we_hit = self.ser_io.receive(self.boom_handler)

        if not ok:
            self.err_out()
            return

        send_sf_records = False
        they_hit = False
        if not we_won:
            # update fire-solution
            self.fs.update(xy, we_hit)
            if we_hit:
                logging.info("we HIT  @{}".format(xy))
                self.hit_counter += 1
                max_hits = sum(map(lambda x: x[0]*x[1], nr_ships.items()))
                if self.hit_counter >= max_hits:
                    raise RuntimeError("According to you we've hit more than {} times, but you never sent the SF records".format(max_hits))
            else:
                logging.info("we MISS @{}".format(xy))
                
            # now pray as they shoot at us
            ok,xy = self.ser_io.receive(self.hitmiss_handler)
            if not ok:
                self.err_out()
                return

            # update our field accordingly, send messages later, when we know whether we lost or not
            they_hit = self.f.shot_at(*xy)
            if they_hit:
                logging.info("they HIT  @{}".format(xy))
            else:
                logging.info("they MISS @{}".format(xy))

            logging.info("Our Gamefield\n: {}".format(self.f))
        else:
            # now that we've won alredy we send our SF records to the opponent
            send_sf_records = True


        # we check win/loss condition
        we_lost = False
        if self.f.ships_left() == 0:
            logging.info("we have no ships left, we just lost the game")
            send_sf_records = True
            we_lost = True


        if send_sf_records:
            # when we've lost or when we've won we need to send our SF records, do it
            for sfl in self.f.get_sf_records():
                self.ser_io.send_line("HD_{}".format(sfl))
        else:
            if they_hit:
                self.ser_io.send_line("HD_BOOM_H")
            else:
                self.ser_io.send_line("HD_BOOM_M")

        if we_lost:
            # i case we just lost the round we can now receive their SF records
            self.their_r = {}
            for _ in range(0, self.f.sz):
                # read more of those messaged, one has already been received
                self.ser_io.receive(self.sf_handler)

            # raises if data is not correct
            self.validate_their_r()

        if we_lost or we_won:
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

            # now that we know opponents Checksum create our fire-solution, and pass in their_cs, we may use it
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
    args = parser.parse_args()


    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif args.tournament:
        logging.basicConfig(level=logging.WARN)
    else:
        logging.basicConfig(level=logging.INFO)


    # try to open the serial port
    ser_io = SerialIO(args)

    # create the protocol state machine
    sm = StateMachine(ser_io)

    main(sm, args)
