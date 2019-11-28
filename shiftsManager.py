# -*- coding: utf-8 -*-
import base64
import calendar
import configparser
import copy
import datetime
import io
import json
import math
import mimetypes
import operator
import os
import random
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.MIMEText import MIMEText

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from httplib2 import Http
from oauth2client import client, file, tools
from time import sleep

config = configparser.ConfigParser()
config.read('config.ini')

SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/calendar',
          'https://mail.google.com/	']

# The precentage of all days in month that it fair to have difference between
# you and the minimal placement people
shiftsSummary = ['משמרת בוקר', 'משמרת לילה', 'סופ"ש']
NIGHT_TIME = int(config['DEFAULT']['NIGHT_TIME'])
SHIFT_POINTS = [int(config['SHIFT_POINTS']['DAY']), int(config['SHIFT_POINTS']['NIGHT']), int(config['SHIFT_POINTS']['WEEKEND'])]  # Day, night, weekend

class person:
    name = ''
    phone = ''
    email = ''
    canWeekend = True
    canNights = True
    constraints = []
    team = []
    count = 0

    def __init__(self, name = '', phone = '', email = '', canWeekend = True, canNights = True, constraints = [], team = [], count = 0):
        self.name = name   # String
        self.phone = phone # String
        self.email = email # String
        self.canWeekend = canWeekend # Boolean
        self.canNights = canNights # Boolean
        self.constraints = constraints # Array of dates [1,2,3]
        self.team = team # Array of teams
        self.count = count # int

    def __str__(self):
        return 'name: {}, phone: {}, email: {}, canWeekend: {}, canNights: {}, constraints: {}, team: {}, count: {}'.format(
                self.name, self.phone, self.email, self.canWeekend, self.canNights, self.constraints, self.team, self.count)

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

def random_op(temp_placement, people_array, running_team):
    legal_placement = False
    while not legal_placement:
        random_day = random.choice(days)
        random_person = random.choice(people_array)

        legal_placement = can_be_placed(random_day, random_person, running_team)
        
    temp_placement[random_day] = random_person

def hill_climbing(people_array, running_team, running_times = 10000):
    # inital state
    placement = {}
    for day in days:
        placement[day] = None

    placement_utility = utility(placement, people_array)

    run_index = 0
    while run_index < running_times:
        temp_placement = copy.deepcopy(placement)
        random_op(temp_placement, people_array, running_team)
        temp_op_utility = utility(temp_placement, people_array)

        if temp_op_utility < placement_utility:
            placement = temp_placement
            placement_utility = temp_op_utility

        print running_team + " - " + str(run_index)
        run_index += 1

    return placement

def utility(placement, people_array):
    tmp_counts = calculate_scores(placement, people_array)

    run_unresolved = 0
    for day in days:
        if placement[day] == None:
            run_unresolved +=1

    count_sum = 0
    for p in tmp_counts.values():
        count_sum += p
    count_avg = count_sum / len(people_array)

    variance = 0
    for p in tmp_counts.values():
        variance += pow(p - count_avg, 2)
    variance = math.sqrt(float(variance) / len(people_array)) # Higher mean least equal placement 

    del tmp_counts # HACKER MAN

    return 10 * run_unresolved + variance # Higher is worst

# Check if people can be place in this day
def can_be_placed(day, person, team):
    if not (team in person.team):
        return False

    # Check if person have constraint on this day
    if day.day in person.constraints:
        return False

    if day.hour == NIGHT_TIME and person.canNights == 'False':
        return False

    if day.weekday() in [4, 5] and person.canWeekend == 'False':
        return False

    # thursday night shift count as weekend
    if day.weekday() == 3 and day.hour == NIGHT_TIME and person.canWeekend == 'False':
        return False

    return True

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

    COLUMN_HEADERS = rows[0].split(",")

    people_array = []

    # i for rows, each row is a person in the csv
    for i in xrange(1, len(rows)):
        p = person()
        row = rows[i]

        # col for column in the csv.
        for col in xrange(len(row.split(","))):
            if COLUMN_HEADERS[col] == "constraints":
                # constraint_col is an array of strings
                constraint_col = row.split(",")[col].split(' ')
                const = []

                # If someone does not have constraints
                if constraint_col[0] == '':
                    const = [0]
                else:
                    # Checking for hyphen that indicate range
                    for const_value in constraint_col:
                        if '-' in const_value:
                            # Split the hyphen into 2 dates
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

                p.constraints = const

            elif COLUMN_HEADERS[col] == "count":
                p.count = int(row.split(",")[col])

            elif COLUMN_HEADERS[col] == 'team':
                p.team = row.split(",")[col].split(' ')

            elif hasattr(p, COLUMN_HEADERS[col]):
                setattr(p, COLUMN_HEADERS[col], row.split(",")[col])

        people_array.append(p)
    return people_array

def send_invite(placement):
    service = get_service('calendar','v3')
    colors = ['4','10','11']
    for day_index in xrange(len(days) - 1):
        if placement[days[day_index]]: # If its not None - there is people in this day
            if "@" in placement[days[day_index]].email:
                eventObj = {}
                eventObj["start"] = {"dateTime": get_date_string(days[day_index]), "timeZone": "Asia/Jerusalem"}
                eventObj["end"] = {}
                eventObj["end"] = {"dateTime": get_date_string(days[day_index + 1]), "timeZone": "Asia/Jerusalem"}
                eventObj["attendees"] = [{"email": placement[days[day_index]].email}]
                event_type = get_event_type(days[day_index])
                eventObj["summary"] = shiftsSummary[event_type]
                eventObj['colorId'] = colors[event_type]
                eventObj["transparency"] = "transparent"
                event = service.events().insert(calendarId='primary', body=eventObj).execute()
                sleep(2)
                print 'Event ' + event['id'] + ' sent successfully to ' + event['attendees'][0]['email']

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

def send_message(placement, people_array, path, team):
    body = ''
    score_array = calculate_scores(placement, people_array)
    for people in score_array:
        body += people + ":" +  str(score_array[people]) + "\n"

    unresolved_count = 0
    tmp = ''
    for day in days:
        if not placement[day]:
            unresolved_count += 1
            tmp += day.strftime('%d-%m-%Y') + ", "
    if unresolved_count > 0:
        body += 'You got ' + str(unresolved_count) + ' unresolved date/s, you better handle them before publishing! \n'
        body += tmp

    message = MIMEMultipart()
    msg = MIMEText(body)
    message['to'] = str(config['DEFAULT']['EMAIL'])
    message['from'] = str(config['DEFAULT']['EMAIL'])
    message['subject'] = team + " - " + days[0].strftime('%d-%m-%Y')
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

def create_csv(placement, team_name):
    headers = 'טלפון,שם,סוג,יום,תאריך'
    headers += '\n'
    content = ''

    for day in days:
        if not placement[day]:
            content += 'Unresolved,Unresolved,'
            content += shiftsSummary[get_event_type(day)] + ","
            content += day.strftime('%A') + ','
            content += day.strftime('%d-%m-%Y') + '\n'
        else:
            content += placement[day].phone + ","
            content += placement[day].name + ","
            content += shiftsSummary[get_event_type(day)] + ","
            content += day.strftime('%A') + ','
            content += day.strftime('%d-%m-%Y') + '\n'

    PATH = '/tmp/'
    PATH += days[0].strftime('%d-%m-%Y')
    PATH += "-" + str(team_name)
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

def print_finished(team_placement, people_array):
    for team in team_placement:
        unresolved_count = 0
        for day in days:
            print '{} : {}'.format(day.strftime('%d-%m-%Y'), team_placement[team][day].email if team_placement[team][day] else 'Unresolved')
            if team_placement[team][day] == None:
                unresolved_count += 1
        print calculate_scores(team_placement[team], people_array)
        print 'Unresolved count is: {}'.format(unresolved_count)

def post_placement(team_placement):
    response = 'n'
    response = raw_input("commit? [y/n] ")
    if response == 'y':
        for team in team_placement:
            path = create_csv(team_placement[team], team)
    response = raw_input("commit? [y/n] ")
    if response == 'y':
        for team in team_placement:
            path = create_csv(team_placement[team], team)
            send_invite(team_placement[team])
            #send_message(team_placement[team], people_array, path, team)



def calculate_scores(placement, people_array):
    tmp_counts = {}
    for p in people_array:
        tmp_counts[p.email] = 0

    for day in days:
        person = placement[day]

        if person:
            tmp_counts[person.email] += get_shift_score(day)

    return tmp_counts

def get_teams(people_array):
    teams = []
    for p in people_array:
        for team in p.team:
            if team not in teams:
                teams.append(team)

    return teams

def run(people_array):
    teams = get_teams(people_array)
    team_placement = {}
    
    for team in teams:
        team_placement[team] = hill_climbing(people_array, team)

    return team_placement

if __name__ == '__main__':
    initialize_days()
    people_array = get_constraints_from_drive()

    team_placement = run(people_array)
    
    print_finished(team_placement, people_array)
    post_placement(team_placement)
