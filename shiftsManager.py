# -*- coding: utf-8 -*-
import base64
import calendar
import copy
import datetime
import io
import json
import mimetypes
import os
import random
import operator
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.MIMEText import MIMEText

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from httplib2 import Http
from oauth2client import client, file, tools

import configparser
config = configparser.ConfigParser()
config.read('config.ini')

SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/calendar',
          'https://mail.google.com/	']

# The precentage of all days in month that it fair to have difference between
# you and the minimal placement people
fairnessLevel = int(config['DEFAULT']['fairnessLevel'])
shiftsSummary = ['תורנות בוקר', 'תורנות לילה', 'תורנות שבת']
NIGHT_TIME = int(config['DEFAULT']['NIGHT_TIME'])
placement = {}
unresolvedCount = 0
SHIFT_POINTS = [int(config['SHIFT_POINTS']['DAY']), int(config['SHIFT_POINTS']['NIGHT']), int(config['SHIFT_POINTS']['WEEKEND'])]  # Day, night, weekend
ITERATIONS_TIMES = int(config['DEFAULT']['ITERATIONS_TIMES'])

def initialize_days():
    today = datetime.datetime.now()

    month = today.month
    year = today.year

    if(today.month + 1 > 12):
        month = 1
        year = today.year + 1
    else:
        month += 1

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

def get_shift_score(shift):
    score = SHIFT_POINTS[0]
    if shift.hour == NIGHT_TIME:
        score = SHIFT_POINTS[1]
    elif shift.weekday() in [4, 5]:
        score = SHIFT_POINTS[2]

    return score

def recursive_backtracking(day, index,team):

    i = 0
    random.shuffle(peoples)

    while(i < len(peoples)):
        isPlaceable = can_be_placed(day, peoples[i],team)

        if day in placement:
            if(index + 1 < len(days)):
                index += 1
                answer = recursive_backtracking(days[index], index,team)
                if answer:
                    return answer
            else:
                return True

        if(isPlaceable):

            temp = copy.deepcopy(peoples[i])
            #placement[day] = peoples[i]
            placement[day] = temp

            score = get_shift_score(day)
            peoples[i]["Count"] += score

            if(index + 1 < len(days)):
                index += 1
                answer = recursive_backtracking(days[index], index,team)
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
            return recursive_backtracking(days[index], index,team)

    return False

def utility(run):
    const = float(10)/ float(62)
    res = float(run["unresolved"])

    min = float("infinity")
    for people in run["peoples"]:
        if people["Count"] < min:
            min = people["Count"]

    sum_of_diff = 0
    for people in run["peoples"]:
        sum_of_diff += people["Count"] - min
    avg = sum_of_diff / len(run["peoples"])

    avg_diff = float(avg)
    return const * res + float(pow((const * avg_diff),2))

# Check if people can be place in this day
def can_be_placed(day, people,team):

    if not (team in people['Team']):
        return False

    # Check if he have constraint on this day
    if (day.day in people["Constraints"]):
        return False

    ## If he has placed x days more then the lowest placed person then he cant
    ## be placed this day.
    ## X is the toal days in the month divided by the fairness level.
    ## for example: if the fairness level is 10, and there is 30 days in the month
    ## then the difference between you and the lowest can be 3 days.
    #minPlacement = get_minimum()
    #precentage = float(fairnessLevel) / 100
    #if(people["Count"] > ((daysRange[1] * precentage) + minPlacement)):
    #    return False

    if(day.hour == NIGHT_TIME and people["canNights"] == "False"):
        return False

    if(day.weekday() in [4, 5] and people["canWeekend"] == "False"):
        return False

    return True

# Get the lowest placement count
def get_minimum():
    min = len(days) + 1
    for people in peoples:
        if(people["Count"] < min):
            min = people["Count"]
    return min

def get_constraints_from_drive():
    day_name_array = list(calendar.day_abbr)
    day_name_array = [x.lower() for x in day_name_array]

    service = get_service('drive', 'v3')
    file_id = str(config['DEFAULT']['CONSTRAINTS_FILE'])
    request = service.files().export_media(fileId=file_id, mimeType='text/csv')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print "Download %d%%." % int(status.progress() * 100)

    rows = fh.getvalue().split("\r\n")

    COLS = rows[0].split(",")
    global CONSTRAINTS
    CONSTRAINTS = {"peoples": []}

    # i for rows, each row is a person in the csv
    for i in xrange(1, len(rows)):

        row = rows[i]
        CONSTRAINTS["peoples"].append({})

        # col for column in the csv.
        for col in xrange(len(row.split(","))):
            if COLS[col] == "Constraints":
                # constraint_col is an array of strings
                constraint_col = row.split(",")[col].split(' ')
                const = []

                # If someone does not have constraints
                if constraint_col[0] == '':
                    const = [0]
                else:
                    # Checking for hypen that indecate range
                    for const_value in constraint_col:
                        if '-' in const_value:
                            # Split the hypen into 2 dates
                            const_range_days = const_value.split('-')

                            # Create new array from that days
                            const_range = range(int(const_range_days[0]),int(const_range_days[1]) + 1)

                            # Concatenating the arrays
                            const = const + const_range
                        elif isinstance(const_value,str) and const_value.lower() in day_name_array:
                            repeat_const = []
                            const_value = const_value.lower()
                            for day in days:
                                if day_name_array[day.weekday()] == const_value:
                                    repeat_const.append(day.day)

                            # filter the array to unique value
                            repeat_const = list(set(repeat_const))
                            repeat_const.sort()
                            const = const + repeat_const
                        else:
                            const.append(int(const_value))

                CONSTRAINTS["peoples"][i - 1][COLS[col]] = const

            elif COLS[col] == "Count":
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = int(row.split(",")[col])
            elif COLS[col] == 'Team':
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = row.split(",")[col].split(' ')
            else:
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = row.split(",")[col]

    print(CONSTRAINTS)

def send_invite(bestRun):
    service = get_service('calendar','v3')
    colors = ['4','10','11']
    for dayIndex in xrange(len(days) - 1):
        if bestRun['placements'][days[dayIndex]] != 'Unresolved':
            if "@" in bestRun['placements'][days[dayIndex]]['Email']:
                eventObj = {}
                eventObj["start"] = {"dateTime": get_date_string(days[dayIndex]), "timeZone": "Asia/Jerusalem"}
                eventObj["end"] = {}
                eventObj["end"] = {"dateTime": get_date_string(days[dayIndex + 1]), "timeZone": "Asia/Jerusalem"}
                eventObj["attendees"] = [{"email": bestRun['placements'][days[dayIndex]]['Email']}]
                event_type = get_event_type(days[dayIndex])
                eventObj["summary"] = shiftsSummary[event_type]
                eventObj['colorId'] = colors[event_type]
                eventObj["transparency"] = "transparent"
                service.events().insert(calendarId='primary', body=eventObj).execute()

def get_event_type(day):
    if day.weekday() in [4, 5]:
        return 2
    if str(day.hour) == '20':
        return 1
    if str(day.hour) == '8':
        return 0

def get_date_string(date):
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

def send_message(bestRun,path):
    body = ''
    for people in bestRun["peoples"]:
        body += people["Name"] + ":" + str(people["Count"]) + "\n"

    if bestRun['unresolved'] == 0:
        body += 'You got zero unresolved date to handle!'
    else:
        body += 'You got ' + str(bestRun['unresolved']) + ' unresolved date/s, you better handle them before publishing! \n'
        for day in days:
            if bestRun['placements'][day] == 'Unresolved':
                body += day.strftime('%d-%m-%Y')

    message = MIMEMultipart()
    msg = MIMEText(body)
    message['to'] = str(config['DEFAULT']['EMAIL'])
    message['from'] = str(config['DEFAULT']['EMAIL'])
    message['subject'] = str(days[0])
    message.attach(msg)

    content_type, encoding = mimetypes.guess_type(path)
    if content_type is None or encoding is not None:
        content_type = 'application/octet-stream'
    main_type, sub_type = content_type.split('/', 1)
    fp = open(path, 'rb')
    msg = MIMEBase(main_type, sub_type)
    msg.set_payload(fp.read())
    fp.close()
    filename = os.path.basename(path)
    msg.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(msg)
    message = {'raw': base64.urlsafe_b64encode(message.as_string())}

    service = get_service('gmail','v1')
    message = (service.users().messages().send(userId='me', body=message).execute())
    print 'Message Id: %s' % message['id']

def create_csv(bestRun,team):
    headers = 'טלפון,שם,סוג,יום,תאריך'
    headers += '\n'
    content = ''

    for day in days:
        if bestRun['placements'][day] == 'Unresolved':
            content += 'Unresolved,Unresolved,'
            content += shiftsSummary[get_event_type(day)] + ","
            content += day.strftime('%A') + ','
            content += day.strftime('%d-%m-%Y') + '\n'
        else:
            content += bestRun['placements'][day]['Phone'] + ","
            content += bestRun['placements'][day]['Name'] + ","
            content += shiftsSummary[get_event_type(day)] + ","
            content += day.strftime('%A') + ','
            content += day.strftime('%d-%m-%Y') + '\n'

    PATH = '/tmp/'
    PATH += days[0].strftime('%d-%m-%Y')
    PATH += "-" + str(team)
    PATH += '.csv'
    f = open(PATH,'w')
    f.write(headers + content)
    f.close()
    return PATH

def get_service(api,version):
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build(api, version, http=creds.authorize(Http()))
    return service

def print_finished(bestRun):
    for day in days:
        print("" + str(day) + "  " + str(bestRun["placements"][day]))

    print("#######################")
    for people in bestRun["peoples"]:
        print(people["Name"] + ":" + str(people["Count"]))

    print("Unresolved count:" + str(bestRun['unresolved']))

    if bestRun['unresolved'] != 0:
        for day in days:
            if bestRun['placements'][day] == 'Unresolved':
                print(day.strftime('%d-%m-%Y'))

def post_placement(bestRun,team):

    path = create_csv(bestRun,team)
    response = 'n'
    response = raw_input("commit? [y/n]")
    if response == 'y':
        send_invite(bestRun)
        send_message(bestRun,path)

def get_teams(people):
    teams = []
    for person in people['peoples']:
        for team in person['Team']:
            if team not in teams:
                teams.append(team)

    return teams

if __name__ == '__main__':
    initialize_days()
    get_constraints_from_drive()
    times = 0
    iterations = []

    teams = get_teams(CONSTRAINTS)
    teams_best_runs = {}
    for team in teams:

        minUtil = float("infinity")
        bestRun = None

        teams_people = copy.deepcopy(CONSTRAINTS)
        teams_people = teams_people["peoples"]

        # Check if people is existing in more than one team, if he does then copy all of his shift from the already placed team
        # to the new team and delete him from the new team available people to place
        template = {}
        if teams_best_runs != {}:
                for day in days:
                    for compare_team in teams_best_runs.keys():
                        if teams_best_runs[compare_team]['placements'][day] != 'Unresolved':
                            if team in teams_best_runs[compare_team]['placements'][day]['Team']:
                                template[day] = copy.deepcopy(teams_best_runs[compare_team]['placements'][day])
                                people_to_remove_index = teams_people.index(template[day]) if template[day] in teams_people else -1
                                if people_to_remove_index != -1:
                                    teams_people.pop(people_to_remove_index)

        peoples = teams_people
        for times in xrange(ITERATIONS_TIMES):
            
            index = 0
            placement = template
            global unresolvedCount
            unresolvedCount = 0
            recursive_backtracking(days[index], index,team)
            currRun = {"placements": copy.deepcopy(placement), "unresolved": copy.deepcopy(unresolvedCount), "peoples": peoples}
            utilValue = utility(currRun)

            if utilValue < minUtil:
                minUtil = utilValue
                bestRun = currRun

            print times

        teams_best_runs[team] = copy.deepcopy(bestRun)

    for team in teams:
        print (team)
        print_finished(teams_best_runs[team])
    for team in teams:
        post_placement(teams_best_runs[team],team)
