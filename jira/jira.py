#!/usr/bin/python

import base64
import json
import urllib
import urlparse
import httplib

DEBUG_FUNC = None

class JIRA:
    def __init__(self, endpoint, username=None, password=None):
        self.endpoint = endpoint
        self.username = username
        self.password = password

    def search(self, jql, offset=None, limit=None, fields=None, expand=None):
        return self.callJiraAPI("GET", "/rest/api/2/search?"
                                + "jql=" + urllib.quote(jql)
                                + ("&fields={0}".format(urllib.quote(','.join(fields))) if fields else "")
                                + ("&expand={0}".format(urllib.quote(','.join(expand))) if expand else "")
                                + ("&startAt={0}".format(offset) if offset else "")
                                + ("&maxResults={0}".format(limit) if limit else ""))

    def getFields(self):
        return self.callJiraAPI("GET", "/rest/api/2/field")

    def getRepositoryCommits(self, issueId):
        return self.callJiraAPI("GET", "/rest/dev-status/1.0/issue/detail?"
                                + "issueId=" + urllib.quote(issueId)
                                + "&applicationType=stash&dataType=repository"
                                )["detail"][0]["repositories"]

    def getComments(self, issueKey):
        return self.callJiraAPI("GET", "/rest/api/2/issue/{0}/comment".format(issueKey))

    def updateComment(self, issueKey, commentId, text):
        return self.callJiraAPI(
            "PUT", "/rest/api/2/issue/{0}/comment/{1}".format(issueKey, commentId),
            {"body": text}
        )

    def addComment(self, issueKey, text):
        return self.callJiraAPI(
            "POST", "/rest/api/2/issue/{0}/comment".format(issueKey),
            {"body": text}
        )

    def callJiraAPI(self, method, resource, body=None):
        authHeader = base64.b64encode(self.username + ":" + self.password) if self.username else None
        statusCode, data = self.callAPI(self.endpoint, method, resource, body, authHeader)
        return data

    def callAPI(self, endpoint, method, resource, body=None, authHeader=None):
        headers = {}
        bodyData = None
        if body is not None:
            bodyData = json.dumps(body)
            headers["Content-Type"] = "application/json"
            
        if authHeader is not None:
            headers["Authorization"] = "Basic " + authHeader

        endp = urlparse.urlparse(endpoint)
        if not endp.netloc:
            endp = urlparse.urlparse("//" + endpoint)

        MakeConnection = httplib.HTTPSConnection
        if 'http' == endp.scheme:
            MakeConnection = httplib.HTTPConnection
        connection = MakeConnection(endp.netloc, timeout=10)

        connection.request(method, resource, bodyData, headers)
        response = connection.getresponse()
        statusCode, data = response.status, response.read()
        connection.close()
        
        if DEBUG_FUNC:
            DEBUG_FUNC("{0} {1}\n{2}".format(method, resource, data))
        return statusCode, json.loads(data)
