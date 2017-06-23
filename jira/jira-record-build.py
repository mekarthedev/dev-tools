#!/usr/bin/env python2.7

import jira
import json
import sys
import re
from optparse import OptionParser
import unittest

DEBUG = False

class Tests(unittest.TestCase):
    def addCommentMock(self):
        def mock(ticketKey, bodyText):
            self.addedComments.append((ticketKey, bodyText))
        return mock

    def updateCommentMock(self):
        def mock(ticketKey, commentId, bodyText):
            self.updatedComments.append((ticketKey, commentId, bodyText))
        return mock

    def setUp(self):
        self.addedComments = []
        self.updatedComments = []

    def test_onNoPreviousRecords_addsNewRecord(self):
        jiraClient = lambda: None
        jiraClient.getComments = lambda key: {
            "startAt": 0, "maxResults": 1, "total": 1,
            "comments": [{"id": "1234", "body": "test"}]
        }
        jiraClient.addComment = self.addCommentMock()

        recordBuildInTicket(jiraClient, "KEY-123", "abcd123")
        self.assertEqual(self.addedComments, [("KEY-123", "[Available in builds: abcd123 ]")])

    def test_onExistingRecordAndNewBuild_addsBuildToExisitingRecord(self):
        jiraClient = lambda: None
        jiraClient.getComments = lambda key: {
            "startAt": 0, "maxResults": 1, "total": 1,
            "comments": [{"id": "comm1234", "body": "[Available in builds: abcd123 ]"}]
        }
        jiraClient.updateComment = self.updateCommentMock()

        recordBuildInTicket(jiraClient, "KEY-123", "xyz")
        self.assertEqual(self.updatedComments, [("KEY-123", "comm1234", "[Available in builds: abcd123, xyz ]")])

    def test_onExistingRecordForSameBuild_doesNothing(self):
        jiraClient = lambda: None
        jiraClient.getComments = lambda key: {
            "startAt": 0, "maxResults": 1, "total": 1,
            "comments": [{"id": "comm1234", "body": "[Available in builds: abcd123 ]"}]
        }
        jiraClient.updateComment = self.updateCommentMock()

        recordBuildInTicket(jiraClient, "KEY-123", "abcd123")
        self.assertEqual(self.updatedComments, [])

def recordBuildInTicket(jiraClient, ticketKey, buildId):

    comments = jiraClient.getComments(ticketKey)

    existingComment = None
    existingBuildsMatch = None
    for comment in comments["comments"]:
        existingBuildsMatch = re.search(r"\[Available in builds: (?P<builds>.*) \]", comment["body"])
        if existingBuildsMatch:
            existingComment = comment
            logDebug("existingComment: " + str(existingComment))
            break

    if existingComment:
        existingBuilds = existingBuildsMatch.group("builds").split(", ")
        logDebug("existingBuilds: " + str(existingBuilds))
        if buildId not in existingBuilds:
            existingBuilds.append(buildId)
            updatedText = "[Available in builds: {0} ]".format(", ".join(existingBuilds))
            jiraClient.updateComment(ticketKey, existingComment["id"], updatedText)
    else:
        jiraClient.addComment(ticketKey, "[Available in builds: {0} ]".format(buildId))

def logDebug(msg):
    if DEBUG:
        for line in msg.split('\n'):
            sys.stderr.write("[DEBUG] " + line + "\n")

if __name__ == '__main__':
    opt_parser = OptionParser(usage="%prog [options]",
                              description="Records a new build information into each JIRA issue. "
                                          "After adding record, you may use JQL to e.g. look up tickets fixed in specific build. "
                                          "Reads issues list from STDIN - see output format of jira-find.")

    opt_parser.add_option("--build", action="store", default=None, metavar="BUILD_ID", help="The identifier of the build to be attached to tickets.")
    opt_parser.add_option("--user", action="store", default=None, metavar="USER:PWD", help="Login credentials.")

    opt_parser.add_option("--test", action="store_true", default=False, help="Run self-testing & diagnostics.")
    opt_parser.add_option("--debug", action="store_true", default=False, help="Run in debug mode. Additional information will be printed to stderr.")

    opts, args = opt_parser.parse_args()
    if opts.test:
        suite = unittest.TestLoader().loadTestsFromTestCase(Tests)
        unittest.TextTestRunner(verbosity=2).run(suite)

    elif opts.build:
        DEBUG = opts.debug
        if DEBUG:
            jira.DEBUG_FUNC = logDebug

        tickets = json.loads(sys.stdin.read())
        if len(tickets) > 0:
            jiraEndpoint = tickets[0]["endpoint"]
            credentials = opts.user.split(":", 1) if opts.user else [None, None]
            jiraClient = jira.JIRA(jiraEndpoint, credentials[0], credentials[1] if len(credentials) > 1 else None)

        for ticket in tickets:
            recordBuildInTicket(jiraClient, ticket["key"], opts.build)


    else:
        opt_parser.print_help()