# -*- coding: utf-8 -*-
import calendar
import datetime
import json
import os
import copy
import random
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from httplib2 import Http
from oauth2client import file, client, tools

SCOPES = ['https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/calendar']

# The precentage of all days in month that it fair to have difference between
# you and the minimal placement people
global fairnessLevel
fairnessLevel = 10

global NIGHT_TIME
NIGHT_TIME = 20

global placement
placement = {}

global unresolvedCount
unresolvedCount = 0

global SHIFT_POINTS
SHIFT_POINTS = [1, 1.5, 2]  # Day, night, weekend

global ITERATIONS_TIMES
ITERATIONS_TIMES = 100


def initializeDays():
    today = datetime.datetime.now()

    month = today.month
    year = today.year

    if(today.month + 1 > 12):
        month = 1
        year = today.year + 1

    global daysRange
    daysRange = calendar.monthrange(year, month)

    # Datetime.date with isoweekday start with monday = 0
    global days
    dayArray = [datetime.datetime(year, month, day)
                for day in range(1, daysRange[1] + 1)]
    days = []

    for day in dayArray:
        # Weekend
        if(day.weekday() in [4, 5]):
            days.append(day)
        else:
            morningShift = copy.deepcopy(day)
            nightShift = copy.deepcopy(day)
            morningShift = morningShift.replace(hour=8)
            nightShift = nightShift.replace(hour=20)

            days.append(morningShift)
            days.append(nightShift)

def getShiftScore(shift):
    score = SHIFT_POINTS[0]
    if shift.hour == NIGHT_TIME:
        score = SHIFT_POINTS[1]
    elif shift.weekday() in [4, 5]:
        score = SHIFT_POINTS[2]

    return score

def recursiveBackTracking(day, index):

    i = 0
    random.shuffle(peoples)

    while(i < len(peoples)):
        isPlaceable = canBePlaced(day, peoples[i])
        if(isPlaceable):

            temp = copy.deepcopy(peoples[i])
            #placement[day] = peoples[i]
            placement[day] = temp

            score = getShiftScore(day)
            peoples[i]["count"] += score

            if(index + 1 < len(days)):
                index += 1
                answer = recursiveBackTracking(days[index], index)
                if answer:
                    return answer
            else:
                return True
        i += 1
    if(i >= len(peoples)):
        placement[day] = "Unresolved"
        global unresolvedCount
        unresolvedCount += 1
        if(index + 1 < len(days)):
            index += 1
            return recursiveBackTracking(days[index], index)

    return False

# Check if people can be place in this day
def canBePlaced(day, people):

    # Check if he have constraint on this day
    if (day.day in people["constraints"]):
        return False

    # If he has placed x days more then the lowest placed person then he cant
    # be placed this day.
    # X is the toal days in the month divided by the fairness level.
    # for example: if the fairness level is 10, and there is 30 days in the month
    # then the difference between you and the lowest can be 3 days.
    minPlacement = getMinimum()
    if(people["count"] > (daysRange[1]/fairnessLevel + minPlacement)):
        return False

    if(day.hour == NIGHT_TIME and people["canNights"] == "False"):
        return False

    if(day.weekday() in [4, 5] and people["canWeekend"] == "False"):
        return False

    return True

# Get the lowest placement count
def getMinimum():
    min = daysRange[1] + 1
    for people in peoples:
        if(people["count"] < min):
            min = people["count"]
    return min

def getConstraintsFromDrive():

    store = file.Storage('token.json')
    creds = store.get()

    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('drive', 'v3', http=creds.authorize(Http()))

    file_id = 'X'
    request = service.files().export_media(fileId=file_id,
                                             mimeType='text/csv')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print "Download %d%%." % int(status.progress() * 100)

    csvf = fh.getvalue()
    rows = csvf.split("\r\n")
    
    COLS = rows[0].split(",")
    global CONSTRAINTS
    CONSTRAINTS = {"peoples": []}
    for i in xrange(1,len(rows)):
        row = rows[i]
        CONSTRAINTS["peoples"].append({})
        for col in xrange(len(row.split(","))):
            if COLS[col] == "constraints":
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = row.split(",")[col].split(" ")
                constraintsLength = len(CONSTRAINTS["peoples"][i - 1][COLS[col]])
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = map(int,CONSTRAINTS["peoples"][i - 1][COLS[col]])
            elif COLS[col] == "count":
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = int(row.split(",")[col])
            else:
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = row.split(",")[col]

    print(CONSTRAINTS)

def sendInvite(bestRun):
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('calendar', 'v3', http=creds.authorize(Http()))

    shiftsSummary = ['תורנות בוקר','תורנות לילה','תורנות שבת']

    for dayIndex in xrange(len(days) - 1):
        if bestRun['placements'][days[dayIndex]] != 'Unresolved':
            if "@" in bestRun['placements'][days[dayIndex]]['email']:
                eventObj = {}
                eventObj["start"] = {"dateTime": getDateString(days[dayIndex]),"timeZone": "Asia/Jerusalem"}
                eventObj["end"] = {}
                eventObj["end"] = {"dateTime": getDateString(days[dayIndex + 1]),"timeZone": "Asia/Jerusalem"}
                eventObj["attendees"] = [{"email":bestRun['placements'][days[dayIndex]]['email']}]
                eventObj["summary"] = shiftsSummary[getEventType(days[dayIndex])]

                output = service.events().insert(calendarId='primary', body=eventObj).execute()

def getEventType(day):
    if day.weekday() in [4,5]:
        return 2
    if str(day.hour) == '20':
        return 1
    if str(day.hour) == '8':
        return 0

def getDateString(date):
    hour = str(date.hour)
    day = str(date.day)
    month = str(date.month)
    if hour == "8":
        hour = "08"
    if len(day) == 1:
        day = "0" + day
    if len(month) == 1:
        month = "0" + month
    return str(date.year) + "-" + month + "-" + day + "T" + hour + ":00:00"

if __name__ == '__main__':
    initializeDays()
    getConstraintsFromDrive()
    times = 0
    iterations = []
    while unresolvedCount == 0 or times < ITERATIONS_TIMES:
        unresolvedCount = 0
        global peoples
        peoples = copy.deepcopy(CONSTRAINTS)
        peoples = peoples["peoples"]
        index = 0
        placement = {}
        recursiveBackTracking(days[index], index)
        iterations.append({"placements": copy.deepcopy(
            placement), "unresolved": copy.deepcopy(unresolvedCount), "peoples": peoples})
        times += 1

    minUnResolved = len(days) + 1
    bestRun = {}
    for iteration in iterations:
        if iteration["unresolved"] < minUnResolved:
            minUnResolved = iteration["unresolved"]
            bestRun = copy.deepcopy(iteration)

    for day in days:
        print("" + str(day) + "  " + str(bestRun["placements"][day]))

    print("#######################")
    for people in bestRun["peoples"]:
        print(people["Name"] + ":" + str(people["count"]))
    
    sendInvite(bestRun)
