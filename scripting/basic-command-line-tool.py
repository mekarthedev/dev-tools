#!/usr/bin/env python2.7

from optparse import OptionParser
import unittest

DEBUG = False

class Tests(unittest.TestCase):
    def test_sanity(self):
        self.assertEqual(2+2, 4)

    # TODO: Write tests.

def logDebug(msg):
    if DEBUG:
        for line in msg.split('\n'):
            sys.stderr.write("[DEBUG] " + line + "\n")

if __name__ == '__main__':
    opt_parser = OptionParser(usage="%prog [options]",
                              description="")
    opt_parser.add_option("--test", action="store_true", default=False, help="Run self-testing & diagnostics.")
    opt_parser.add_option("--debug", action="store_true", default=False, help="Run in debug mode. Additional information will be printed to stderr.")

    opts, args = opt_parser.parse_args()
    if opts.test:
        suite = unittest.TestLoader().loadTestsFromTestCase(Tests)
        unittest.TextTestRunner(verbosity=2).run(suite)

    elif len(args) >= 1:
        DEBUG = opts.debug

        # TODO: Do the job.

    else:
        opt_parser.print_help()