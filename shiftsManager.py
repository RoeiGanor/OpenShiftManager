import calendar,datetime,json,os,copy,random


# The precentage of all days in month that it fair to have difference between
# you and the minimal placement people
global fairnessLevel
fairnessLevel = 10

global NIGHT_TIME
NIGHT_TIME = 20

global placement
placement = {}

global unresolveCount
unresolveCount = 0

# TODO: Implement days and weekend in the init function
def initializeDays():
    today = datetime.datetime.now()

    month = today.month
    year = today.year

    if(today.month + 1 > 12):
        month = 1
        year = today.year + 1

    global daysRange
    daysRange = calendar.monthrange(year,month)

    # Datetime.date with isoweekday start with monday = 0
    global days
    dayArray = [datetime.datetime(year,month,day) for day in range(1,daysRange[1] + 1)]
    days = []

    for day in dayArray:
        # Weekend
        if(day.weekday() in [4,5]):
            days.append(day)
        else:
            morningShift = copy.deepcopy(day)
            nightShift = copy.deepcopy(day)
            morningShift = morningShift.replace(hour=8)
            nightShift = nightShift.replace(hour=20)

            days.append(morningShift)
            days.append(nightShift)

    print(days) # DEBUG

# Load the constraints file
def getConstraints():
    dirPath = os.path.dirname(os.path.realpath(__file__))
    filePath = os.path.join(dirPath,"constraints.json")
    global peoples
    with open(filePath) as f:
        peoples = json.load(f)

def recursiveBackTracking(day,index):
    print(day.day)
    i = 0

    random.shuffle(peoples)

    while(i < len(peoples)):
        print(peoples[i]["name"])
        isPlaceable = canBePlaced(day,peoples[i])
        print(""+str(isPlaceable) + " " + str(day.day) + " " + peoples[i]["name"])
        if(isPlaceable):

            temp = copy.deepcopy(peoples[i])
            #placement[day] = peoples[i]
            placement[day] = temp

            peoples[i]["count"] +=1

            print("" + peoples[i]["name"] + " " + str(peoples[i]["count"]))
            if(index + 1 < len(days)):
                index += 1
                answer = recursiveBackTracking(days[index],index)
                if answer:
                    return answer
            else:
                return True
        i += 1
    if(i >= len(peoples)):
          placement[day] = "Unresolved"
          unresolveCount = 0
          if(index + 1 < len(days)):
                index += 1
                return recursiveBackTracking(days[index],index)

    return False

# Check if people can be place in this day
def canBePlaced(day,people):

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

    if(day.weekday() in [4,5] and people["canWeekend"] == "False"):
        return False

    return True

    #return day.day not in people["constraints"]

# Get the lowest placement count
def getMinimum():
    min = daysRange[1] + 1
    for people in peoples:
        if(people["count"] < min):
            min = people["count"]
    return min


if __name__ == '__main__':
    initializeDays()
    getConstraints()
    peoples = peoples["peoples"]

    index = 0

    recursiveBackTracking(days[index],index)

    for day in days:
        print("" + str(day) + "\/ " + str(placement[day]))

    print("kader Points")

    for people in peoples:
        print(people["name"] + ":" + str(people["count"]))


    
