import atexit
import json
import urllib.request

from flask import (
    Flask,
    render_template,
    request,
    jsonify
)
from flask_api import status
import datetime, time
import csv
from apscheduler.schedulers.background import BackgroundScheduler
import logging

#Importing file database (TinyDB) 
from tinydb import TinyDB, Query, where
import os
dir_path = os.path.dirname(os.path.realpath(__file__))
db_path = os.path.join(dir_path,"data.db")


log = logging.getLogger('apscheduler.executors.default')
log.setLevel(logging.INFO)  # DEBUG

fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
h = logging.StreamHandler()
h.setFormatter(fmt)
log.addHandler(h)

# Create the application instance
app = Flask(__name__, template_folder="")

# Create a URL route in our application for "/"
@app.route('/')
def home():
    """
    This function just responds to the browser ULR
    localhost:5000/

    :return:        the rendered template 'home.html'
    """
    return render_template('index.html')


@app.route('/results')
def results():
    return render_template('results.html')


@app.route('/today', methods=['POST', 'GET'])
def today():
    # return today's voting results
    date = get_todays_date()
    return jsonify(get_resuts_by_date(date))


@app.route('/getresults', methods=['POST', 'GET'])
def get_results():
    date = request.args['date']

    return jsonify(get_resuts_by_date(date))


@app.route('/getall', methods=['GET'])
def get_all_results():
    results = []
    #query TinyDB instead of CSV file

    with TinyDB(db_path,'dates') as db:
        dates = []
        
        for i in db.all():
            results.append(get_resuts_by_date(i["date"]))
            dates.append(i["date"])
            
        return jsonify({"data": results, "dates": dates})


@app.route('/voted', methods=['POST', 'GET'])
def voted():
    #using real request IP instead
    my_ip = str(request.environ.get('HTTP_X_REAL_IP', request.remote_addr))

    if has_voted(my_ip):
        return "True"
    else:
        return "False"


@app.route('/poll', methods=['POST', 'GET'])
def poll():
    vote = request.args['answer']
    #using real request IP instead
    ip = str(request.environ.get('HTTP_X_REAL_IP', request.remote_addr))
    
    # no need to check if ip is valid anymore, but stricter vote check
    if vote not in ["bull","bear"]:
        return status.HTTP_400_BAD_REQUEST

    date = get_todays_date()

    # ensure client hasn't voted yet
    if not has_voted(ip):
        # using db instead of csv
        with TinyDB(db_path,'voting') as db:
            # insert vote into database
            db.insert({"ip":ip,"vote":vote,"date":date})
            # insert date again into database for future performance in get_all_results
            db = db.table('dates')
            if not db.count(where('date') == date):
                db.insert({"date":date})
    return render_template('results.html')


@app.route('/market', methods=['GET'])
def market():
    mkt_data = get_market_data()
    return jsonify(mkt_data)


# checks if vote has been made
def has_voted(ip):
    date = get_todays_date()
    #check if ip has voted in db, returns int 
    with TinyDB(db_path,'voting') as db:
        return db.count((where('date') == date) & (where('ip') == ip))

# gets results by date
def get_resuts_by_date(date):
    # using db instead csv and query for totals by specific date
    with TinyDB(db_path,'voting') as db:
        bullCount = db.count((where('date') == date) & (where('vote') == "bull"))
        bearCount = db.count((where('date') == date) & (where('vote') == "bear"))
        return {"date": date, "bullCount": bullCount, "bearCount": bearCount}


def get_market_data():
    quotes = {}
    csv_name = "market_data.csv"
    with open(csv_name) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            quotes[row[0]] = row[1]
    return quotes


# for job scheduling
scheduler = BackgroundScheduler()


# run this after market hours
def job():
    print("Fetching...")

    todays_date = str(datetime.datetime.now())[:10]
    apiKey = ""
    with open("creds.txt") as creds:
        apiKey = creds.read().replace("\n", '')
    url = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=SPY&apikey=" + apiKey

    contents = urllib.request.urlopen(url).read()

    time.sleep(0.1)

    parsed = json.loads(contents)

    time.sleep(0.1)

    parsed = parsed["Time Series (Daily)"]

    offset = 1

    previous_date = str(datetime.datetime.now() - datetime.timedelta(days=1))[:10]
    previous_offset = 1

    while previous_date not in parsed:
        previous_offset += 1
        previous_date = str(datetime.datetime.now() - datetime.timedelta(days=previous_offset))[:10]

    previous_close = 0

    if todays_date in parsed:
        data = parsed[todays_date]
        previous_close = parsed[previous_date]["4. close"]

        mktopen = data["1. open"]
        close = data["4. close"]
        pct = str(float(close) / float(previous_close) - 1)

        fdate = (datetime.datetime.now()).strftime("%m/%d/%Y")

        mkt_data = str(fdate) + "," + str(pct)

    else:
        mkt_data = get_todays_date() + "," + "N/A"

    print(mkt_data)
    # append to csv
    f = open('market_data.csv', 'a')
    f.write(mkt_data + '\n')

    # repeat in 24 hours
    scheduler.add_job(func=job, trigger="date",
                                        run_date=datetime.datetime.now() + datetime.timedelta(days=1, seconds=-0.2))


def get_todays_date():
    date_url = "http://worldclockapi.com/api/json/est/now"
    contents = json.loads(urllib.request.urlopen(date_url).read())
    date = contents['currentDateTime'][:10]
    date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%m/%d/%Y")
    return date


# If we're running in stand alone mode, run the application
if __name__ == '__main__':
    print(get_todays_date())
    scheduler.add_job(func=job, trigger="date", run_date = datetime.datetime.now())
    scheduler.start()

    app.run(debug=False, host='0.0.0.0')

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())
