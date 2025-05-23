#!/bin/sh

# socat -d -d pty,raw,echo=0 pty,raw,echo=0

if false; then
	# trigger win in host
	echo DH_START_RL > $1
	sleep 1
	echo DH_CS_1711636203 > $1
	sleep 1
	echo DH_BOOM_H > $1
	sleep 1
	echo DH_BOOM_1_2 > $1
	sleep 1
	echo DH_SF0D0000000002 > $1
	echo DH_SF1D5555502002 > $1
	echo DH_SF2D0000002000 > $1
	echo DH_SF3D0000000004 > $1
	echo DH_SF4D4030333004 > $1
	echo DH_SF5D4030000004 > $1
	echo DH_SF6D4030220204 > $1
	echo DH_SF7D4000000200 > $1
	echo DH_SF8D0000000000 > $1
	echo DH_SF9D0000333000 > $1
fi

if true; then
	# trigger loss in host
	echo DH_START_RL > $1
	echo DH_CS_1711636203 > $1

	for i in 0 1 2 3 4 5 6 7 8 9; do
		for j in 0 1 2 3 4 5 6 7 8 9; do
			echo DH_BOOM_M > $1
			echo DH_BOOM_${i}_${j} > $1
		done
	done
fi

if false; then
	# trigger cheater in host 
	echo DH_START_RL > $1
	echo DH_CS_1711636203 > $1

	for i in 0 1 2 3 4 5 6 7 8 9; do
		for j in 0 1 2 3 4 5 6 7 8 9; do
			echo DH_BOOM_M > $1
			echo DH_BOOM_1_1 > $1
		done
	done
fi










