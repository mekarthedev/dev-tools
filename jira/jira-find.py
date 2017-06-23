#!/usr/bin/python

import jira
import json
import os
import re
import subprocess as sp
import sys
import operator
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

class GitModule:
    def __init__(self, url, path, headRevision):
        self.url = url
        self.path = path
        self.head = headRevision

class RevisionSpecifier:
    def __init__(self, revision):
        self.revision = revision
        self.module = None
        self.isReachable = False

def findRevisionsSpecified(jiraClient, issues, fields):
    revisions = {}
    for issue in issues:
        foundRevs = []

        # search through issue fields

        def findRevisions(fieldValue):
            for gitCommit in re.finditer(r"(?<!\w)[a-z0-9]{40}(?!\w)", fieldValue):
                foundRevs.append(RevisionSpecifier(gitCommit.group(0)))
                logDebug("Found rev {0} in field {1} of issue {2}".format(gitCommit.group(0), fieldName, issue['key']))

        for fieldName in fields:
            field = issue['fields'][fieldName] if fieldName in issue['fields'] else None
            if field is not None:
                if 'comment' == fieldName:
                    for comment in field['comments']:
                        findRevisions(comment['body'])
                else:
                    findRevisions(field)

        # search through bitbucket

        relatedCommits = jiraClient.getRepositoryCommits(issue["id"])
        for repositoryGroup in relatedCommits:
            nonMerges = [commit for commit in repositoryGroup["commits"] if not commit["merge"]]
            if len(nonMerges) > 0:
                latestCommit = sorted(nonMerges, key=operator.itemgetter("authorTimestamp"), reverse=True)[0]
                foundRevs.append(RevisionSpecifier(latestCommit["id"]))

        revisions[issue['key']] = foundRevs

    return revisions

def verifyRevisions(revisions, modules):
    """
    Checks the validity of the revisions specified. The valid revisions will get their module info filled in.
    """
    for issueKey, revSpecifiers in revisions.iteritems():
        for rev in revSpecifiers:
            for module in modules:
                _, isValid = execCommand("git rev-parse --verify {0}^{{commit}}".format(rev.revision), isQuery = True, cwd=module.path)
                isValid = not isValid  # invert shell's 0 for True
                if isValid:
                    rev.module = module
                    
    return revisions

def verifyReachability(revisions):
    """
    Checks if the revision is reachable from the head of its module.
    """
    for issueKey, revSpecifiers in revisions.iteritems():
        for rev in revSpecifiers:
            if rev.module:
                _, isReachable = execCommand("git merge-base --is-ancestor {0} {1}".format(rev.revision, rev.module.head), isQuery = True, cwd=rev.module.path)
                rev.isReachable = not isReachable  # invert shell's 0 for True
                if rev.isReachable:
                    logDebug(issueKey + " is reachable at " + rev.revision + " in " + rev.module.url)
                    
    return revisions

def getGitModules(pathToRepo, revision, outModules=[]):
    logDebug("Found module '" + pathToRepo + "' in rev " + revision)

    repoURL, _ = execCommand("git config --local --get remote.origin.url", isQuery=True, cwd=pathToRepo)
    outModules.append(GitModule(repoURL, pathToRepo, revision))
    
    submodulesStr, _ = execCommand('git config -f .gitmodules --get-regexp ^submodule.*path$', isQuery=True, cwd=pathToRepo)
    submodules = [os.path.join(pathToRepo, kvPair.split(' ', 1)[1]) for kvPair in submodulesStr.split('\n')] if submodulesStr else []
    for modulePath in submodules:
        moduleInfo, _ = execCommand('git ls-tree {0} {1}'.format(revision, modulePath), isQuery=True, cwd=pathToRepo)
        moduleRevision = re.match('\\d+ commit (?P<revision>.{40})\t', moduleInfo).group('revision')
        getGitModules(modulePath, moduleRevision, outModules)

    return outModules

def filterReachables(revisions):
    reachables = {}
    for issueKey, revSpecifiers in revisions.iteritems():
        for rev in revSpecifiers:
            if rev.module and rev.isReachable:
                reachables[issueKey] = revSpecifiers

    logDebug("Reachables: " + str(reachables))
    return reachables

def filterUnreachables(revisions):
    unreachables = {}
    for issueKey, revSpecifiers in revisions.iteritems():
        issueIsReachable = False
        for rev in revSpecifiers:
            if rev.module and rev.isReachable:
                issueIsReachable = True
                break

        if not issueIsReachable:
            unreachables[issueKey] = revSpecifiers
            
    logDebug("Unreachables: " + str(unreachables))
    return unreachables

def filterOrphants(revisions):
    orphants = {}
    for issueKey, revSpecifiers in revisions.iteritems():
        hasValidRevisions = False
        for rev in revSpecifiers:
            if rev.module:
                hasValidRevisions = True
                break
        
        if not hasValidRevisions:
            orphants[issueKey] = revSpecifiers
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
    for issueKey, revSpecifiers in reachables.iteritems():
        issue = [i for i in issues if i['key'] == issueKey][0]
        fields = issue['fields']
        for rev in revSpecifiers:
            reachablesJSON.append({
                'key': issueKey,
                'endpoint': jiraEndpoint,
                'summary': fields['summary'],
                'resolution': fields['resolution']['name'] if fields['resolution'] else 'Unresolved',
                'revision': rev.revision,
                'repository': rev.module.url if rev.module else None})
    print json.dumps(reachablesJSON)

if __name__ == '__main__':
    opt_parser = OptionParser(usage="%prog [options] JIRA_ENDPOINT JIRA_QUERY [GIT_REPO_PATH]",
                              description="Lists issues resolved for the given git revision."
                              " Lists only issues matching given JQL query."
                              " Default schema is https unless explicitly defined in JIRA_ENDPOINT."
                              " The result is in JSON format. Use git-jira-format to get human-readable form.")
    opt_parser.add_option("--search-in", action="append", default=[], metavar="FIELD",
                          help="A ticket field where revision ID should be searched for. This could be field id or field name."
                          " E.g. comment, My Custom Field, customfield_10202.")
    opt_parser.add_option("--revision", action="store", default="HEAD", metavar="GIT_REF",
                          help="A revison of the root repository against which all the checks should be performed."
                          " The submodules will be checked against revisions they had in this revision of the root.")
    
    opt_parser.add_option("--unreachable", action="store_true", default=False,
                          help="Search tickets that are valid but not reachable from the given repository head."
                          " Useful in finding tickets that have their Fix Version/s set to some version"
                          " but are not actualy present in that version.")
    opt_parser.add_option("--orphants", action="store_true", default=False,
                          help="Search tickets with no valid git revision specified."
                          " Useful with 'resolution = Fixed or resolution = Complete' criteria.")
    
    opt_parser.add_option("--user", action="store", default=None, metavar="USER:PWD", help="Login credentials.")
    
    opt_parser.add_option("--debug", action="store_true", default=False, help="Run in debug mode. Additional information will be printed to stderr.")

    opts, args = opt_parser.parse_args()
    if len(args) >= 2:
        DEBUG = opts.debug
        if DEBUG:
            jira.DEBUG_FUNC = logDebug

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

        if not opts.search_in:
            opts.search_in = ['comment']

        credentials = opts.user.split(":", 1) if opts.user else [None, None]
        jiraClient = jira.JIRA(jiraEndpoint, credentials[0], credentials[1] if len(credentials) > 1 else None)
        fields = getFieldIDs(jiraClient, opts.search_in)
        issues = getAllIssues(jiraClient, jiraQuery, set(['summary', 'resolution'] + fields))
        revisions = findRevisionsSpecified(jiraClient, issues, fields)
        gitModules = getGitModules(repoRootPath, opts.revision)
        verifiedRevisions = verifyRevisions(revisions, gitModules)
        verifiedRevisions = verifyReachability(revisions)

        filteredIssues = {}
        
        if opts.orphants:
            filteredIssues.update(filterOrphants(verifiedRevisions))
        if opts.unreachable:
            filteredIssues.update(filterUnreachables(verifiedRevisions))
            
        if not opts.orphants and not opts.unreachable:
            filteredIssues.update(filterReachables(verifiedRevisions))

        printIssues(issues, filteredIssues)

    else:
        opt_parser.print_help()
