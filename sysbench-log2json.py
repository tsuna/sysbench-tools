#!/usr/bin/python
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

"""Parse sysbench's output and transform it into JSON."""

import json
import os
import re
import sys


TOBYTES = {
  "K": 1024,
  "M": 1024 * 1024,
  "G": 1024 * 1024 * 1024,
  "T": 1024 * 1024 * 1024 * 1024,
}

TESTS = {
  "seqrd": "Sequential reads",
  "seqwr": "Sequential writes",
  "rndrd": "Random reads",
  "rndwr": "Random writes",
  "rndrw": "Random reads/writes",
}

METRICS = (
  #("num_threads", "Number of threads"),
  #("test_mode", "Test mode"),
  #("total_size", "Data size"),
  #("block_size", "Block size"),
  ("nread", "Number of reads"),
  ("nwrite", "Number of writes"),
  ("nother", "Number of other operations"),
  ("ntotal", "Total number of operations"),
  ("readb", "Bytes read"),
  ("writeb", "Bytes written"),
  ("totalb", "Total bytes"),
  ("throughput", "Throughput"),
  ("iops", "IOPS"),
  #("total_time", "Total time"),
  ("total_num_events", "Total number of events"),
  #("total_exec_time", "Total execution time"),
  ("req_min", "Min. latency"),
  ("req_avg", "Avg. latency"),
  ("req_max", "Max. latency"),
  ("req_95p", "95th percentile latency"),
  # Derived metrics
  ("nreadps", "Reads/s"),
  ("nwriteps", "Writes/s"),
)

SORTED_METRICS = tuple(metric for metric, description in METRICS)
METRICS = dict(METRICS)

def tobytes(s):
  """Helper to convert, say, "1.42Mb" into `1488977.92'."""
  if "A" <= s[-2] <= "Z":
    return float(s[:-2]) * TOBYTES[s[-2]]
  return int(s[:-1])


def toms(s):
  """Helper to convert, say, "1.42s" into `1420'."""
  if s.endswith("ms"):
    return float(s[:-2])
  return float(s[:-1]) * 1000  # sec -> msec


def process(f, results):
  """Populate the results dict with data parsed from the file."""
  test_mode = num_threads = block_size = total_size = None
  per_req_stats = None

  data = None
  def record(metric, value):
    data[metric].setdefault(num_threads, []).append(value)

  line = None
  def match(regexp):
    m = re.match(regexp, line.strip())
    assert m, "%r did not match %r" % (line.strip(), regexp)
    return m

  for line in f:
    if line.endswith("run\n"):
      sysbench_args = dict(arg.lstrip("-").split("=", 1)
                           for arg in line.split()
                           if "=" in arg)
      num_threads = int(sysbench_args["num-threads"])
      block_size = int(sysbench_args["file-block-size"])
      total_size = sysbench_args["file-total-size"]
      test_mode = sysbench_args["file-test-mode"]
      if test_mode not in results:
        data = dict((metric, {}) for metric in METRICS)
        results[test_mode] = {
          "block_size": block_size,
          "total_size": total_size,
          "results": data,
        }
      else:
        assert block_size == results[test_mode]["block_size"]
        assert total_size == results[test_mode]["total_size"]
        data = results[test_mode]["results"]
    elif test_mode is None:
      continue
    elif line.startswith("Operations performed"):
      m = match("Operations performed:"
                "\s*(\d+) [Rr]eads?, (\d+) [Ww]rites?, (\d+)"
                "\s*Other = (\d+) Total")
      nread, nwrite, nother, ntotal = map(int, m.groups())
      record("nread", nread)
      record("nwrite", nwrite)
      record("nother", nother)
      record("ntotal", ntotal)
    elif line.startswith("Read "):
      m = match("Read ([0-9.]+\w?b)"
                "\s*Written ([0-9.]+\w?b)"
                "\s*Total transferred ([0-9.]+\w?b)"
                "\s*\(([0-9.]+\w?b)/sec\)")
      readb, writeb, totalb, throughput = map(tobytes, m.groups())
      record("readb", readb)
      record("writeb", writeb)
      record("totalb", totalb)
      record("throughput", throughput)
    elif line.endswith("executed\n"):
      record("iops", float(line.split()[0]))
    elif line.startswith("    total time:"):
      total_time = toms(line.split()[-1])
      #record("total_time", total_time)
      total_time /= 1000
      record("nreadps", nread / total_time)
      record("nwriteps", nwrite / total_time)
    elif line.startswith("    total number of events:"):
      record("total_num_events", int(line.split()[-1]))
    #elif line.startswith("    total time taken by event execution:"):
    #  record("total_exec_time", float(line.split()[-1]))
    elif line in ("    per-request statistics:\n", "    response time:\n"):
      per_req_stats = True
    elif line == "\n":
      per_req_stats = False
    elif per_req_stats and ":" in line:
      stat, value = line.split(":")
      stat = stat.strip()
      value = toms(value.strip())
      if stat == "min":
        record("req_min", value)
      elif stat == "avg":
        record("req_avg", value)
      elif stat == "max":
        record("req_max", value)
      elif stat == "approx.  95 percentile":
        record("req_95p", value)
      else:
        assert False, repr(stat)


def main(args):
  args.pop(0)
  if not args:
    print >>sys.stderr, "Need at least one file in argument"
    return 1
  # maps a config name to results for this config
  config2results = {}
  for arg in args:
    config = os.path.basename(os.path.dirname(arg))
    if not config:
      print >>sys.stderr, ("Error: %r needs to be in a directory named after"
                           " the config name" % (arg))
      return 2
    if config not in config2results:
      config2results[config] = {}
    with open(arg) as f:
      process(f, config2results[config])

  for config, results in config2results.iteritems():
    for test_mode, data in results.iteritems():
      data["averages"] = dict((metric, [[num_threads, sum(vs) / len(vs)]
                                        for num_threads, vs in sorted(values.iteritems())])
                              for metric, values in data["results"].iteritems())
  with open("results.js", "w") as f:
    f.write("TESTS = ");
    json.dump(TESTS, f, indent=2)
    f.write(";\nMETRICS = {\n");
    f.write("\n".join('  "%s": "%s",' % (metric, METRICS[metric])
                      for metric in SORTED_METRICS))
    f.write("\n};\nresults = ");
    json.dump(config2results, f, indent=2)
    f.write(";")


if __name__ == "__main__":
  sys.exit(main(sys.argv))
