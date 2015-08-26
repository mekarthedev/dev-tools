#!/usr/bin/python

import jira
import json
import os
import re
import subprocess as sp
import sys
import urlparse
from optparse import OptionParser

DEBUG = False

def getFieldIDs(client, rawNames):
    fields = client.getFields()
    names = dict([(f['name'], f['id']) for f in fields])
    IDs = set([f['id'] for f in fields])
    filtered = []
    for name in rawNames:
        if name in IDs:
            filtered.append(name)
        elif name in names:
            filtered.append(names[name])
    logDebug("Fields: " + str(filtered))
    return filtered

def getAllIssues(client, query, fields):
    issues = []
    while True:
        found = client.search(query, len(issues), 128, fields)
        issues.extend(found['issues'])
        if 0 == len(found['issues']):
            break
    return issues

def findRevisionsSpecified(issues, fields):
    revisions = {}
    for issue in issues:
        foundRevs = []
        def findRevisions(fieldValue):
            for gitCommit in re.finditer(r"(?<!\w)[a-z0-9]{40}(?!\w)", fieldValue):
                foundRevs.append(gitCommit.group(0))
                logDebug("Found rev {0} in field {1} of issue {2}".format(gitCommit.group(0), fieldName, issue['key']))

        for fieldName in fields:
            field = issue['fields'][fieldName] if fieldName in issue['fields'] else None
            if field is not None:
                if 'comment' == fieldName:
                    for comment in field['comments']:
                        findRevisions(comment['body'])
                else:
                    findRevisions(field)

        revisions[issue['key']] = foundRevs

    return revisions

def verifyRevisions(revisions, modules):
    verifiedRevisions = {}
    for issueKey, revs in revisions.iteritems():
        checkedRevs = []
        for rev in revs:
            module = None
            for path, head in modules:
                _, isValid = execCommand("git rev-parse --verify {0}^{{commit}}".format(rev), isQuery = True, cwd=path)
                isValid = not isValid  # invert shell's 0 for True
                if isValid:
                    module = path, head
                    break
            checkedRevs.append((rev, module))
        verifiedRevisions[issueKey] = checkedRevs

    logDebug("Verified map: " + str(verifiedRevisions))
    return verifiedRevisions

def getGitModules(pathToRepo, revision, outModules=[]):
    logDebug("Found module '" + pathToRepo + "' in rev " + revision)
    outModules.append((pathToRepo, revision))
    submodulesStr, _ = execCommand('git config -f .gitmodules --get-regexp ^submodule.*path$', isQuery=True, cwd=pathToRepo)
    submodules = [os.path.join(pathToRepo, kvPair.split(' ', 1)[1]) for kvPair in submodulesStr.split('\n')] if submodulesStr else []
    for modulePath in submodules:
        moduleInfo, _ = execCommand('git ls-tree {0} {1}'.format(revision, modulePath), isQuery=True, cwd=pathToRepo)
        moduleRevision = re.match('\\d+ commit (?P<revision>.{40})\t', moduleInfo).group('revision')
        getGitModules(modulePath, moduleRevision, outModules)

    return outModules

def findReachables(revisions):
    reachables = []
    for key, revs in revisions.iteritems():
        for rev, repo in revs:
            if repo:
                repoPath, repoHead = repo
                repoURL, _ = execCommand("git config --local --get remote.origin.url", isQuery=True, cwd=repoPath)
                _, isReachable = execCommand("git merge-base --is-ancestor {0} {1}".format(rev, repoHead), isQuery = True, cwd=repoPath)
                isReachable = not isReachable  # invert shell's 0 for True
                if isReachable:
                    reachables.append((key, rev, repoURL))
                    logDebug(key + " is reachable through " + rev + " in " + repoURL)
    return reachables

def findOrphants(revisions):
    orphants = []
    for issueKey, revs in revisions.iteritems():
        hasValidRevisions = False
        for rev, repo in revs:
            if repo:
                hasValidRevisions = True
                break
        
        if not hasValidRevisions:
            orphants.append((issueKey, None, None))
            logDebug(issueKey + " is an orphant")
    return orphants

def execCommand(command, cwd='.', isQuery=False, raw=False):
    stdout = sp.PIPE if isQuery else sys.stdout
    stderr = open(os.devnull, 'w') if isQuery else sys.stderr
    p = sp.Popen(command, shell=True, cwd=cwd, stdout=stdout, stderr=stderr, stdin=sys.stdin)
    out, _ = p.communicate()
    if not raw:
        out = out.strip()
    logDebug(cwd + " $ " + command + " -> " + str(p.returncode) + ": " + out)
    return out, p.returncode

def logDebug(msg):
    if DEBUG:
        for line in msg.split('\n'):
            sys.stderr.write("[DEBUG] " + line + "\n")

def printIssues(issues, reachables):
    reachablesJSON = []
    for key, rev, repo in reachables:
        issue = [i for i in issues if i['key'] == key][0]
        reachablesJSON.append({
            'key': key,
            'endpoint': jiraEndpoint,
            'summary': issue['fields']['summary'],
            'resolution': issue['fields']['resolution']['name'],
            'revision': rev,
            'repository': repo})
    print json.dumps(reachablesJSON)

if __name__ == '__main__':
    opt_parser = OptionParser(usage="%prog [options] JIRA_ENDPOINT JIRA_QUERY [GIT_REPO_PATH]",
                              description="Lists issues resolved for the given git revision."
                              " Lists only issues matching given JQL query. By default only Resolved tickets will be searched for."
                              " You may alter this behavior by explicitly specifying the 'status' field in the query."
                              " Default schema is https unless explicitly defined in JIRA_ENDPOINT."
                              " The result is in JSON format. Use git-jira-format to get human-readable form.")
    opt_parser.add_option("--search-in", action="append", default=[], metavar="FIELD",
                          help="A ticket field where revision ID should be searched for. This could be field id or field name."
                          " E.g. comment, My Custom Field, customfield_10202.")
    opt_parser.add_option("--revision", action="store", default="HEAD", metavar="GIT_REF",
                          help="A revison of the root repository against which all the checks should be performed."
                          " The submodules will be checked against revisions they had in this revision of the root.")
    opt_parser.add_option("--orphants", action="store_true", default=False,
                          help="Search tickets with no valid git revision specified. Useful with 'resolution = Fixed or resolution = Complete' criteria.")
    opt_parser.add_option("--username", action="store", default=None, metavar="USER", help="A user's credential.")
    opt_parser.add_option("--password", action="store", default=None, metavar="PWD", help="A user's password.")
    opt_parser.add_option("--debug", action="store_true", default=False, help="Run in debug mode. Additional information will be printed to stderr.")

    opts, args = opt_parser.parse_args()
    if len(args) >= 2:
        DEBUG = opts.debug
        if DEBUG:
            jira.LOG_DEBUG = logDebug

        jiraEndpoint = args[0]
        jiraQuery = args[1]
        repoRootPath, _ = execCommand('git rev-parse --show-toplevel', isQuery=True, cwd=(args[2] if len(args) > 2 else '.'))
        opts.revision, _ = execCommand("git rev-parse {0}".format(opts.revision), isQuery=True, cwd=repoRootPath)
        logDebug('repo: {0} revision: {1}'.format(repoRootPath, opts.revision))

        endp = urlparse.urlparse(jiraEndpoint)
        if not endp.netloc:  # simple host definition will be interpreted as path, not as host name
            jiraEndpoint = '//' + jiraEndpoint
        if not endp.scheme:
            jiraEndpoint = 'https:' + jiraEndpoint

        if not re.search(r"(^|\W)status(\W|$)", jiraQuery, re.IGNORECASE):
            jiraQuery = "(" + jiraQuery + ") and status = Resolved"

        if not opts.search_in:
            opts.search_in = ['comment']
        
        jiraClient = jira.JIRA(jiraEndpoint, opts.username, opts.password)
        fields = getFieldIDs(jiraClient, opts.search_in)
        issues = getAllIssues(jiraClient, jiraQuery, set(['summary', 'resolution'] + fields))
        revisions = findRevisionsSpecified(issues, fields)
        gitModules = getGitModules(repoRootPath, opts.revision)
        verifiedRevisions = verifyRevisions(revisions, gitModules)

        if opts.orphants:
            orphants = findOrphants(verifiedRevisions)
            printIssues(issues, orphants)
        else:
            reachables = findReachables(verifiedRevisions)
            printIssues(issues, reachables)

    else:
        opt_parser.print_help()
