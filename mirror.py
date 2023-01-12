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
    if "BB_COOKIES" in os.environ:
        print("cookie already in env var")
        return
    if os.path.exists("bb_cookies.txt"):
        print("Loading cookie from file")
        with open('bb_cookies.txt', 'r') as f:
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
    with open('bb_cookies.txt', 'w') as f:
        json.dump(requests.utils.dict_from_cookiejar(login_response.cookies), f)

def initial_data():
    global sim_data
    global season_id
    global day
    if os.path.exists('sim.json'):
        print("Loading sim_data from file")
        with open('sim.json', 'r') as f:
            sim_data = json.load(f)
        season_id = sim_data['simData']['currentSeasonId']
        day = sim_data['simData']['currentDay']
    else:
        get_sim()

    global game_data
    if os.path.exists('games.json'):
        print("Loading games_data from file")
        with open('games.json', 'r') as f:
            game_data = json.load(f)
    else:
        get_games()

    global teams_data
    if os.path.exists('teams.json'):
        print("Loading teams_data from file")
        with open('teams.json', 'r') as f:
            teams_data = json.load(f)
    else:
        get_teams()

    global players_data
    if os.path.exists('players.json'):
        print("Loading players_data from file")
        with open('players.json', 'r') as f:
            players_data = json.load(f)
    else:
        get_players()


def get_games():
    global game_data
    print("Fetching games")

    games_uri = "https://api2.blaseball.com/seasons/cd1b6714-f4de-4dfc-a030-851b3459d8d1/games"
    for _ in range(REQUEST_RETRIES):
        games_response = requests.get(games_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))
        if games_response.status_code == 500:
            print("Games request failed - retrying")
            time.sleep(REQUEST_RETRY_DELAY)
        else:
            game_data = games_response.json()

            for game in game_data:
                del game["gameEventBatches"]

            with open('games.json', 'w') as f:
                json.dump(game_data, f)
            break
    else:
        print("Games request failed all retries - Not updating")

def get_sim():
    ''' Get and set global sim data (season, day, etc)'''
    global season_id
    global day
    global sim_data
    print("Fetching sim")
    sim_uri = "https://api2.blaseball.com/sim/"
    for _ in range(REQUEST_RETRIES):
        sim_response = requests.get(sim_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))
        if sim_response.status_code == 500:
            print("Sim request failed - retrying")
            time.sleep(REQUEST_RETRY_DELAY)
        else:
            sim_data = sim_response.json()
            season_id = sim_data['simData']['currentSeasonId']
            day = sim_data['simData']['currentDay']

            with open('sim.json', 'w') as f:
                json.dump(sim_data, f)
            break
    else:
        print("Sim request failed all retries - Not updating")

def get_teams():
    global teams_data
    print("Fetching teams")

    divisions = []
    for subleague in sim_data['simData']['currentLeagueData']['subLeagues']:
        divisions.extend(subleague['divisions'])

    teams_uri = f"https://api2.blaseball.com/seasons/{season_id}/days/{day}/teams"
    # There has to be a better way than this
    for _ in range(REQUEST_RETRIES):
        teams_response = requests.get(teams_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))
        if teams_response.status_code == 500:
            print(f"Teams request failed - retrying")
            time.sleep(REQUEST_RETRY_DELAY)
        else:
            teams_response_data = teams_response.json()
            temp_teams_data = []

            for division in divisions:
                division_teams = teams_response_data[division['id']]
                temp_teams_data.extend(division_teams)

            teams_data = temp_teams_data

            with open('teams.json', 'w') as f:
                json.dump(teams_data, f)
            break
    else:
        print("Teams request failed all retries - not updating")
    # If the retries fail, teams_data just doesn't get updated

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

        # There's probably a better way to do this
        for _ in range(REQUEST_RETRIES):
            player_response = requests.get(player_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))
            if player_response.status_code == 500:
                print(f"{player['id']} Player request failed - retrying")
                time.sleep(REQUEST_RETRY_DELAY)
            else:
                player_response_data = player_response.json()
                temp_players_data.append(player_response_data)
                break
        # If it doesn't get a good response, don't add player to temp_player_data
        time.sleep(REQUEST_DELAY)

    players_data = temp_players_data

    with open('players.json', 'w') as f:
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
    return jsonify(game_data)

@app.route("/teams")
def show_teams():
    return jsonify(teams_data)

@app.route("/players")
def show_players():
    return jsonify(players_data)

@app.route("/sim")
def show_sim():
    return jsonify(sim_data)

if __name__ == "__main__":
    set_auth_var()
    initial_data()
    CORS(app)
    app.run(host='0.0.0.0', port=5000)