#!/usr/bin/python

import base64
import json
import urllib
import urlparse
import httplib

LOG_DEBUG = None

class JIRA:
    def __init__(self, endpoint, username=None, password=None):
        self.endpoint = endpoint
        self.username = username
        self.password = password

    def search(self, jql, offset=None, limit=None, fields=None):
        return self.callJiraAPI("GET", "/rest/api/2/search?"
                                + "jql=" + urllib.quote(jql)
                                + ("&fields={0}".format(urllib.quote(','.join(fields))) if fields else "")
                                + ("&startAt={0}".format(offset) if offset else "")
                                + ("&maxResults={0}".format(limit) if limit else ""))

    def getFields(self):
        return self.callJiraAPI("GET", "/rest/api/2/field")

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
        
        if LOG_DEBUG:
            LOG_DEBUG("{0} {1}\n{2}".format(method, resource, data))
        return statusCode, json.loads(data)
