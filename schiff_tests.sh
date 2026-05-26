#!/bin/sh

# socat -d -d pty,raw,echo=0 pty,raw,echo=0

send_frame_ascii() {
    dev="$1"
    id="$2"
    payload="$3"

    python - <<'PY' "$dev" "$id" "$payload"
import sys
path, msgid, payload = sys.argv[1], sys.argv[2], sys.argv[3]
frame = b'#' + msgid.encode('ascii') + bytes([len(payload)]) + payload.encode('ascii')
crc = sum(frame[1:]) & 0xFF
frame += bytes([crc]) + b'$'
with open(path, 'ab') as f:
    f.write(frame)
PY
}

send_frame_bytes() {
    dev="$1"
    id="$2"
    shift 2
    hexbytes="$*"

    python - <<'PY' "$dev" "$id" $hexbytes
import sys
path, msgid = sys.argv[1], sys.argv[2]
bytes_data = bytes(int(x, 16) for x in sys.argv[3:])
frame = b'#' + msgid.encode('ascii') + bytes([len(bytes_data)]) + bytes_data
crc = sum(frame[1:]) & 0xFF
frame += bytes([crc]) + b'$'
with open(path, 'ab') as f:
    f.write(frame)
PY
}

send_sf_row() {
    dev="$1"
    row="$2"
    rowdata="$3"

    python - <<'PY' "$dev" "$row" "$rowdata"
import sys
path, row, rowdata = sys.argv[1], int(sys.argv[2]), sys.argv[3]
payload = bytes([row]) + rowdata.encode('ascii')
frame = b'#' + b'SFR' + bytes([len(payload)]) + payload
crc = sum(frame[1:]) & 0xFF
frame += bytes([crc]) + b'$'
with open(path, 'ab') as f:
    f.write(frame)
PY
}

if false; then
	# trigger win in host
	send_frame_ascii "$1" STR "RL"
	sleep 1
	send_frame_ascii "$1" CSH "1711636203"
	sleep 1
	send_frame_ascii "$1" BMR "H"
	sleep 1
	send_frame_bytes "$1" BOO 01 02
	sleep 1
	send_sf_row "$1" 0 "0000000002"
	send_sf_row "$1" 1 "5555502002"
	send_sf_row "$1" 2 "0000002000"
	send_sf_row "$1" 3 "0000000004"
	send_sf_row "$1" 4 "4030333004"
	send_sf_row "$1" 5 "4030000004"
	send_sf_row "$1" 6 "4030220204"
	send_sf_row "$1" 7 "4000000200"
	send_sf_row "$1" 8 "0000000000"
	send_sf_row "$1" 9 "0000333000"
fi

if true; then
	# trigger loss in host
	send_frame_ascii "$1" STR "RL"
	send_frame_ascii "$1" CSH "1711636203"

	for i in 0 1 2 3 4 5 6 7 8 9; do
		for j in 0 1 2 3 4 5 6 7 8 9; do
			send_frame_ascii "$1" BMR "M"
			send_frame_bytes "$1" BOO "$i" "$j"
		done
	done
fi

if false; then
	# trigger cheater in host
	send_frame_ascii "$1" STR "RL"
	send_frame_ascii "$1" CSH "1711636203"

	for i in 0 1 2 3 4 5 6 7 8 9; do
		for j in 0 1 2 3 4 5 6 7 8 9; do
			send_frame_ascii "$1" BMR "M"
			send_frame_bytes "$1" BOO 01 01
		done
	done
fi










