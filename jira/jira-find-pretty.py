#!/usr/bin/python

import sys
import json
from optparse import OptionParser
import re

def splitTicketKey(key):
    index = 0
    prefix = key
    m = re.search("\d+$", key)
    if m:
        index = int(m.group(0))
        prefix = key[0:(len(key) - len(m.group(0)))]
    return (prefix, index)

if __name__ == '__main__':
    opt_parser = OptionParser(usage="%prog [options]", description="Formats the output of jira-find in human readable format.")
    opts, args = opt_parser.parse_args()

    ticketsMap = {}
    for ticket in json.loads(sys.stdin.read()):
        ticketsMap[ticket['key']] = ticket
    orderedTickets = [ticketsMap[key] for key in sorted(ticketsMap, key=splitTicketKey)]

    for ticket in orderedTickets:
        sys.stdout.write(u'{endpoint}/browse/{key}\n'.format(**ticket).encode("utf-8"))
