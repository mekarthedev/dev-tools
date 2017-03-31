#!/usr/bin/env python2.7

from optparse import OptionParser
import os
import re
import unittest

DEBUG = False

def open2public(source):
    source = re.sub(r"^open class", r"public class", source, flags=re.MULTILINE)
    source = re.sub(r"^(@objc(\([^)]+\))?) open class", r"\1 public class", source, flags=re.MULTILINE)
    source = re.sub(r"    open", r"    public", source)
    source = re.sub(r"    static open", r"    static public", source)
    source = re.sub(r"    override open", r"    override public", source)
    source = re.sub(r"    (@objc(\([^)]+\))?) open", r"    \1 public", source)
    source = re.sub(r"^fileprivate class", r"private class", source, flags=re.MULTILINE)
    source = re.sub(r"    fileprivate", r"    private", source)
    source = re.sub(r" fileprivate\(set\) ", r" private(set) ", source)
    source = re.sub(r"    static fileprivate", r"    static private", source)
    return source

class Tests(unittest.TestCase):
    def testThat_open2public_onSnippetWithOpens_replacesOpensWithPublics(self):
        original = r"""
open class MyClass {
    open var field = "asdf"
    open fileprivate(set) var field2 = 1234
    open init() { }
    open func f() {
        // open class - should stay untouched
    }

    fileprivate var field2 = "asdf"
    fileprivate init(x: Int) { }
    fileprivate func f2() {
    }
}
@objc open class MyClass2 {
    @objc open func fo() {}
}
@objc(asdf) open class MyClass3 {
    static open func fs() {}
    override open func fo() {}
    @objc(asdf:asdf:) open func fobjc() {}
    static fileprivate func fs2() {}
}
        """
        expected = r"""
public class MyClass {
    public var field = "asdf"
    public private(set) var field2 = 1234
    public init() { }
    public func f() {
        // open class - should stay untouched
    }

    private var field2 = "asdf"
    private init(x: Int) { }
    private func f2() {
    }
}
@objc public class MyClass2 {
    @objc public func fo() {}
}
@objc(asdf) public class MyClass3 {
    static public func fs() {}
    override public func fo() {}
    @objc(asdf:asdf:) public func fobjc() {}
    static private func fs2() {}
}
        """
        updated = open2public(original)
        self.assertEqual(updated, expected)

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

        sourceFilePath = args[0]
        print sourceFilePath
        with open(sourceFilePath, 'rb') as sourceFile:
            source = sourceFile.read()
        updatedSource = open2public(source)
        with open(sourceFilePath, 'wb') as sourceFile:
            sourceFile.write(updatedSource)

    else:
        opt_parser.print_help()