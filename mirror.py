import requests
import json
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from flask_cors import CORS

REQUEST_DELAY = 0.1
REQUEST_RETRIES = 3
REQUEST_RETRY_DELAY = 5

sim_data = None
season_id = None
day = None
teams_data = None
players_data = None
game_data = None


def set_auth_var():
    if not os.path.exists("data"):
        os.makedirs("data")
    if "BB_COOKIES" in os.environ:
        print("cookie already in env var")
        return
    if os.path.exists("data/bb_cookies.txt"):
        print("Loading cookie from file")
        with open('data/bb_cookies.txt', 'r') as f:
            os.environ["BB_COOKIES"] = json.dumps(json.load(f))
        return

    login_uri = "https://api2.blaseball.com/auth/sign-in"
    login_payload = {"email": os.environ.get("BB_EMAIL"), "password": os.environ.get("BB_PASSWORD")}
    login_headers = {"content-type": "application/json"}
    print("Making auth request for cookie")
    print(login_payload, login_headers)
    login_response = requests.post(login_uri, data=json.dumps(login_payload), headers=login_headers)
    print(login_response)

    #Dump to ENV. Note that this may not be persistent depending upon OS/implementation
    os.environ["BB_COOKIES"] = json.dumps(requests.utils.dict_from_cookiejar(login_response.cookies))

    #Dump to FILE.
    with open('data/bb_cookies.txt', 'w') as f:
        json.dump(requests.utils.dict_from_cookiejar(login_response.cookies), f)

def initial_data():
    global sim_data
    global season_id
    global day
    if os.path.exists('data/sim.json'):
        print("Loading sim_data from file")
        with open('data/sim.json', 'r') as f:
            sim_data = json.load(f)
        season_id = sim_data['simData']['currentSeasonId']
        day = sim_data['simData']['currentDay']
    else:
        get_sim()

    global game_data
    if os.path.exists('data/games.json'):
        print("Loading games_data from file")
        with open('data/games.json', 'r') as f:
            game_data = json.load(f)
    else:
        get_games()

    global teams_data
    if os.path.exists('data/teams.json'):
        print("Loading teams_data from file")
        with open('data/teams.json', 'r') as f:
            teams_data = json.load(f)
    else:
        get_teams()

    global players_data
    if os.path.exists('data/players.json'):
        print("Loading players_data from file")
        with open('data/players.json', 'r') as f:
            players_data = json.load(f)
    else:
        get_players()


def request_with_retry(url):
    for _ in range(REQUEST_RETRIES):
        response = requests.get(url, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))
        if response.status_code == 500:
            print(f"request to {url} failed - retrying")
            time.sleep(REQUEST_RETRY_DELAY)
        else:
            return response.json()

    else:
        print(f"request to {url} failed all retries - Not updating")

def get_games():
    global game_data
    print("Fetching games")

    game_data = request_with_retry("https://api2.blaseball.com/seasons/cd1b6714-f4de-4dfc-a030-851b3459d8d1/games")
    for game in game_data:
        del game["gameEventBatches"]

    with open('data/games.json', 'w') as f:
        json.dump(game_data, f)


def get_sim():
    ''' Get and set global sim data (season, day, etc)'''
    global season_id
    global day
    global sim_data
    print("Fetching sim")

    sim_data = request_with_retry("https://api2.blaseball.com/sim/")
    season_id = sim_data['simData']['currentSeasonId']
    day = sim_data['simData']['currentDay']

    with open('data/sim.json', 'w') as f:
        json.dump(sim_data, f)

def get_teams():
    global teams_data
    print("Fetching teams")

    divisions = []
    for subleague in sim_data['simData']['currentLeagueData']['subLeagues']:
        divisions.extend(subleague['divisions'])

    teams_response_data = request_with_retry(f"https://api2.blaseball.com/seasons/{season_id}/days/{day}/teams")
    temp_teams_data = []

    for division in divisions:
        division_teams = teams_response_data[division['id']]
        temp_teams_data.extend(division_teams)

    teams_data = temp_teams_data

    with open('data/teams.json', 'w') as f:
        json.dump(teams_data, f)

def get_players():
    global players_data
    print("Fetching players")

    roster_players = []
    for team in teams_data:
        roster_players.extend(team['roster'])

    temp_players_data = []
    for player in roster_players:
        if len(temp_players_data) % 10 == 0:
            print(f'{len(temp_players_data)} of {len(roster_players)}...')

        player_uri = f"https://api2.blaseball.com/seasons/{season_id}/days/{day}/players/{player['id']}"

        player_response_data = request_with_retry(player_uri)
        temp_players_data.append(player_response_data)

    players_data = temp_players_data

    with open('data/players.json', 'w') as f:
        json.dump(players_data, f)

sched = BackgroundScheduler(daemon=True)
sched.add_job(get_sim,'interval',minutes=20)
sched.add_job(get_teams,'interval',minutes=20)
sched.add_job(get_players,'interval',minutes=60)
sched.add_job(get_games,'interval',minutes=20)
sched.start()

app = Flask(__name__)

@app.route("/games")
def show_games():
    response = jsonify(game_data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route("/teams")
def show_teams():
    response = jsonify(teams_data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route("/players")
def show_players():
    response = jsonify(players_data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route("/sim")
def show_sim():
    response = jsonify(sim_data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

if __name__ == "__main__":
    set_auth_var()
    initial_data()
    CORS(app)
    app.run(host='0.0.0.0', port=5000)