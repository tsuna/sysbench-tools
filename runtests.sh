#!/bin/sh
# Copyright (C) 2011  Benoit Sigoure
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Sample script to run sysbench.
# In this script, we want to test 3 different devices, all mounted on the same
# machine.  You can adapt this script to other situations easily.  The only
# thing to keep in mind is that each different configuration you're testing
# must log its output to a different directory.

set -u
set -x

OUTDIR="$HOME/out"

size=100G
blksize=16384
devices='hitachi western seagate'
parallel() {
  for device in $devices; do
    cd /mnt/$device/tsuna || exit
    mkdir -p "$OUTDIR/$device" || exit
    sysbench --test=fileio --file-num=64 --file-total-size=$size "$@" &
  done
  for device in $devices; do
    wait
  done
}
parallel cleanup
parallel prepare
sleep 60  # let drives quiesce after prepare

modes='rndrd seqrd seqwr rndrd rndwr rndrw'
for mode in $modes; do
  for device in $devices; do
    cd /mnt/$device/tsuna
    for threads in 1 2 4 8 16 32; do
      exec >$OUTDIR/$device/$device-$size-$mode-$threads 2>&1
      echo "`date` TESTING direct-$mode-$threads"
      for i in 1 2 3 4; do
        echo "`date` start iteration $i"
        sysbench --test=fileio --file-total-size=$size --file-test-mode=$mode \
          --max-time=180 --max-requests=100000000 --num-threads=$threads \
          --init-rng=on --file-num=64 --file-extra-flags=direct \
          --file-fsync-freq=0 --file-block-size=$blksize run 
      done
      echo "`date` DONE TESTING direct-$mode-$threads"
    done
    sleep 45
  done
  # date | mail -s "$mode benchmarks done" your@email.here
done
