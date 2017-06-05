#!/usr/bin/env python

import unittest

from apt_repoman.repo import Repo


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo('testbucket')

    def testGetPkgPathname(self):
        self.assertEqual(
            self.repo._get_pkg_pathname('foo', 'bar', 'baz'),
            'pool/baz/f/foo/bar')


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(RepoTest)
    unittest.TextTestRunner(verbosity=2).run(suite)
