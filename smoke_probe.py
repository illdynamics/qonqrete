#!/usr/bin/env python3
"""QonQrete smoke probe.

A single self-contained Python 3 script using only the standard library
(argparse, sys). It never reads or writes files, makes no network calls,
and reads only sys.argv.
"""

import argparse
import sys

VERSION = '0.1.0'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='smoke_probe.py',
        description='QonQrete smoke probe; exercises the harness end-to-end.',
    )
    parser.add_argument(
        '--version', '-v',
        action='store_true',
        help='print the version and exit',
    )

    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0

    print('QonQrete smoke probe ready')
    return 0


if __name__ == '__main__':
    sys.exit(main())
