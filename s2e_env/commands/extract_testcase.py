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
import string
import StringIO
import struct
import json
from collections import OrderedDict

from s2e_env.command import ProjectCommand, CommandError
from s2e_env.execution_trace import parse as parse_execution_tree
from s2e_env.execution_trace import TraceEntries_pb2

logger = logging.getLogger('extract_testcase')

class TestCasesInTrace:
    """
    Represent all the test cases in a trace file.
    """

    def __init__(self):
        self.test_cases = []

    def add_test_case(self, test_case):
        self.test_cases.append(test_case)

    def sort(self):
        for test_case in self.test_cases:
            test_case.key_values.sort()
        self.test_cases.sort()

    def __len__(self):
        return len(self.test_cases)

    def __iter__(self):
        self.idx = 0
        return self

    def next(self):
        if self.idx < len(self.test_cases):
            test_case = self.test_cases[self.idx]
            self.idx += 1
            return test_case
        else:
            raise StopIteration

    def __next__(self):
        return self.next()

    def make_json_dict(self):
        return [test.make_json_dict() for test in self.test_cases]

class TestCaseInTrace:
    """
    Represent one test case in a trace file.
    """

    def __init__(self, state_id):
        self.state_id = state_id
        self.key_values = []

    def add_key_value(self, key_value):
        self.key_values.append(key_value)

    def __gt__(self, test_case2):
        return self.state_id > test_case2.state_id

    def __str__(self):
        return "state_id: {0}\n".format(self.state_id) + "\n".join(str(kv) for kv in self.key_values)

    def __iter__(self):
        self.idx = 0
        return self

    def next(self):
        if self.idx < len(self.key_values):
            key_value = self.key_values[self.idx]
            self.idx += 1
            return key_value
        else:
            raise StopIteration

    def __next__(self):
        return self.next()

    def make_json_dict(self):
        d = OrderedDict()
        d['state_id'] = self.state_id
        d['key_values'] = [kv.make_json_dict() for kv in self.key_values]
        return d

def byte_array_to_int(value):
    l = len(value)
    if l > 8:
        return 0
    v = bytearray(value)
    if l <= 4:
        padding = 4 - l
        struct_format = 'i'   # convert to int type
    else:
        padding = 8 - l
        struct_format = 'l'   # convert to long type
    for i in range(padding):
        v.append(0x00)
    # print '0x' + ''.join(format(x, '02x') for x in v[::-1])
    return struct.unpack('<' + struct_format, v)[0]

class TestCaseKeyValue:
    """
    Represent one symbolic solution (key-value pair) in a trace file.
    """
    def __init__(self, key, value):
        self.key = key
        self.num_bytes = len(value)
        self.value_bytes = value.encode('base64').strip()
        # self.value_int = int(value[::-1].encode('hex'), 16)
        self.value_int = byte_array_to_int(value) 
        self.value_hex = ','.join('0x' + x.encode('hex') for x in value)
        self.value_printable = ''.join(c if c in string.printable else '.' for c in value)

    def __gt__(self, key_value2):
        return self.key > key_value2.key

    def __str__(self):
        return "key: {0}\nnum_bytes: {1}\nvalue_bytes (base64 encoding): {2}\nvalue_int: {3}\nvalue_hex: {4}\nvalue_string: {5}".format(self.key, self.num_bytes, self.value_bytes, self.value_int, self.value_hex, self.value_printable)

    def make_json_dict(self):
        d = OrderedDict()
        d['key'] = self.key
        d['num_bytes'] = self.num_bytes
        d['value_bytes'] = self.value_bytes
        d['value_int'] = self.value_int
        d['value_hex'] = self.value_hex
        d['value_printable'] = self.value_printable
        return d

class Command(ProjectCommand):
    """
    Extract all the test cases from an S2E execution trace.
    """

    help = 'Extract all the test cases from an S2E execution trace.'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument('--indir', default='s2e-last', help='Directory of the execution trace file. By default we use the execution trace in s2e-last.')
        parser.add_argument('--outdir', help='Directory to store the extracted test cases')
        parser.add_argument('-p', '--path-id', action='append', type=int,
                            dest='path_ids',
                            help='Path IDs to include in the trace. This '
                                 'option can be used multiple times to trace '
                                 'multiple path IDs')

    def extract_test_case(self, test_cases, state_id, header, item):
        if header.type == TraceEntries_pb2.TRACE_TESTCASE:
            test_case = TestCaseInTrace(state_id)
            for p in item.items:
                key_value = TestCaseKeyValue(p.key, p.value)
                test_case.add_key_value(key_value)
            test_cases.add_test_case(test_case)
        elif header.type == TraceEntries_pb2.TRACE_FORK:
            for state_id, trace in item.children.iteritems():
                for child_header, child_item in trace:
                    self.extract_test_case(test_cases, state_id, child_header, child_item)

    def handle(self, *args, **options):
        results_dir = self.project_path(options['indir'])
        if not os.path.isdir(results_dir):
            raise CommandError('Results directory %s does not exist' % (results_dir))
        execution_tree = parse_execution_tree(results_dir, path_ids=options['path_ids'])
        if not execution_tree:
            raise CommandError('The execution trace is empty')

        test_cases = TestCasesInTrace()
        for header, item in execution_tree:
            self.extract_test_case(test_cases, 0, header, item)
        test_cases.sort()
        logger.success('Extracted %d test cases', len(test_cases))
        if not options['outdir']:
            # if outdir is not specified, we store the generated test cases in the indir
            outdir = results_dir
        else:
            if not os.path.isdir(options['outdir']):
                raise CommandError('Output directory %s does not exist' % (options['outdir']))
            outdir = options['outdir']
        testid = 0
        for test_case in test_cases:
            print "========="
            print test_case
            test_case_file_name = 'testcase-%06d.json' % (testid)
            with open(os.path.join(outdir, test_case_file_name), 'w') as json_file:
                json.dump(test_case.make_json_dict(), json_file, indent=4)
            testid += 1
        logger.success('Written %d test cases to %s', len(test_cases), outdir)
