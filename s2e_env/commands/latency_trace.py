"""
@author Ryan Huang <huang@cs.jhu.edu>

The Violet Project  

Copyright (c) 2019, Johns Hopkins University - Order Lab.
    All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
import sys
import os
import struct
import csv

from s2e_env.command import ProjectCommand, CommandError
from s2e_env.execution_trace import parse as parse_execution_tree
from s2e_env.execution_trace import TraceEntries_pb2

logger = logging.getLogger('latency_trace')

LATENCY_TRACE_FILE = "LatencyTracer.dat"
LATENCY_TRACE_CSV = "LatencyTracer.csv"
#
# Layout of the binary latency trace file:
#
# int state_id;
# struct callRecord {
#   uint64_t address; // function starting address
#   uint64_t retAddress;
#   uint64_t callerAddress;    // caller's starting address
#   double execution_time;
#   uint64_t acticityId; // unique id for each function call
#   uint64_t parentId;
#   clock_t begin;
# };
# ...
#

# use struct.unpack to parse the binary file
# https://docs.python.org/2/library/struct.html#struct.unpack
STRUCT_FMT = '=iQQQdQQd' # based on the above layout
STRUCT_LEN = struct.calcsize(STRUCT_FMT)
STRUCT_UNPACK = struct.Struct(STRUCT_FMT).unpack_from

class LatencyRecords:
    """
    Represent all call records in a latency trace file.
    """

    def __init__(self):
        self.records = []

    def add_record(self, record):
        self.records.append(record)

    def sort(self):
        self.records.sort()

    def __len__(self):
        return len(self.records)

class LatencyRecord:
    """
    Represent one record in a latency trace file. It should match 
    the definition in s2e-violet-plugins/src/s2e/Plugins/ConfigurationAnalysis/LatencyTracker.h
    """

    def __init__(self, state_id, address, ret_address, caller_address, 
            execution_time, activity_id, parent_id, clock_begin):
        self.state_id = state_id
        self.address = address
        self.ret_address = ret_address
        self.caller_address = caller_address
        self.execution_time = execution_time
        self.activity_id = activity_id
        self.parent_id = parent_id
        self.clock_begin = clock_begin

    def __gt__(self, other):
        return self.state_id > other.state_id

    def __str__(self):
        return "[%d]: <%s, %s, %s, %f, %d, %d, %f>" % (self.state_id, hex(self.address), 
                hex(self.ret_address), hex(self.caller_address), self.execution_time, 
                self.activity_id, self.parent_id, self.clock_begin)

    def csv_header(self):
        return ("state_id", "address", "return_address", "caller_address",
                "execution_time", "activity_id", "parent_id", "clock_begin")

    def csv_entry(self):
        return (self.state_id, hex(self.address), hex(self.ret_address), 
                hex(self.caller_address), self.execution_time, 
                self.activity_id, self.parent_id, self.clock_begin)

class Command(ProjectCommand):
    """
    Extract all the test cases from an S2E execution trace.
    """

    help = 'Extract all the test cases from an S2E execution trace.'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('--indir', default='s2e-last', help='Directory of the execution trace file. By default we use the execution trace in s2e-last.')
        parser.add_argument('--outdir', help='Directory to store the extracted latency results')

    def parse_latency_trace_file(self, trace_file):
        records = LatencyRecords()
        with open(trace_file, "rb") as tf:
            while True:
                # reading the size of one trace record at a time
                data = tf.read(STRUCT_LEN)
                # if not enough data is available
                if not data:
                    break
                if len(data) != STRUCT_LEN:
                    logger.error("Not enough bytes to deserialize, expecting %d \
                            bytes, got %d bytes" % (STRUCT_LEN, len(data)))
                    break
                result = STRUCT_UNPACK(data)
                record = LatencyRecord(*result)
                records.add_record(record)
        return records

    def handle(self, *args, **options):
        results_dir = self.project_path(options['indir'])
        if not os.path.isdir(results_dir):
            raise CommandError('Results directory %s does not exist' % (results_dir))
        latency_file = os.path.join(results_dir, LATENCY_TRACE_FILE)
        if not os.path.isfile(latency_file):
            raise CommandError('The latency trace file does not exist')
        records = self.parse_latency_trace_file(latency_file)
        records.sort()
        logger.success('Parsed %d latency trace records', len(records))
        if not options['outdir']:
            # if outdir is not specified, we store the generated test cases in the indir
            outdir = results_dir
        else:
            if not os.path.isdir(options['outdir']):
                raise CommandError('Output directory %s does not exist' % (options['outdir']))
            outdir = options['outdir']
        csv_file = os.path.join(outdir, LATENCY_TRACE_CSV)
        with open(csv_file, "w") as outf:
            csv_writer = csv.writer(outf, delimiter=",")
            header = None
            for record in records.records:
                if header is None:
                    header = record.csv_header()
                    csv_writer.writerow(header)
                csv_writer.writerow(record.csv_entry())
        logger.success('Written %d latency trace records %s', len(records), csv_file)
