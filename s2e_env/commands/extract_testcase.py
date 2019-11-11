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
import string
import StringIO

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

class TestCaseKeyValue:
    """
    Represent one symbolic solution (key-value pair) in a trace file.
    """

    def __init__(self, key, value):
        self.key = key
        self.num_bytes = len(value)
        self.value = value
        self.value_hex = ','.join('0x' + x.encode('hex') for x in value)
        self.value_printable = ''.join(c if c in string.printable else '.' for c in value)

    def __gt__(self, key_value2):
        return self.key > key_value2.key

    def __str__(self):
        return "key: {0}\nnum_bytes: {1}\nvalue_hex: {2}\nvalue_string: {3}".format(self.key, self.num_bytes, self.value_hex, self.value_printable)

class Command(ProjectCommand):
    """
    Extract all the test cases from an S2E execution trace.
    """

    help = 'Extract all the test cases from an S2E execution trace.'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)

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
        results_dir = self.project_path('s2e-last')
        execution_tree = parse_execution_tree(results_dir, path_ids=options['path_ids'])
        if not execution_tree:
            raise CommandError('The execution trace is empty')

        test_cases = TestCasesInTrace()
        for header, item in execution_tree:
            self.extract_test_case(test_cases, 0, header, item)
        test_cases.sort()
        logger.success('Extracted %d test cases', len(test_cases))
        for test_case in test_cases:
            print "========="
            print test_case
        # TODO: write test case to file
