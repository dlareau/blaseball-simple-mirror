import requests
import json
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from flask_cors import CORS

game_data = {}

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


def get_games():
    global game_data
    print("Fetching games")
    games_uri = "https://api2.blaseball.com/seasons/cd1b6714-f4de-4dfc-a030-851b3459d8d1/games"
    games_response = requests.get(games_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))

    game_data = games_response.json()

    for game in game_data:
        del game["gameEventBatches"]

    with open('games.json', 'w') as f:
        json.dump(game_data, f)

def get_sim():
    ''' Get and set global sim data (season, day, etc)'''
    global season_id
    global day
    global sim_data
    print("Fetching sim")
    sim_uri = "https://api2.blaseball.com/sim/"
    sim_response = requests.get(sim_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))

    sim_data = sim_response.json()
    season_id = sim_data['simData']['currentSeasonId']
    day = sim_data['simData']['currentDay']

    with open('sim.json', 'w') as f:
        json.dump(sim_data, f)

def get_teams():
    global teams_data
    print("Fetching teams")

    divisions = []
    for subleague in sim_data['simData']['currentLeagueData']['subLeagues']:
        divisions.extend(subleague['divisions'])

    teams_uri = f"https://api2.blaseball.com/seasons/{season_id}/days/{day}/teams"
    teams_response = requests.get(teams_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))

    teams_reponse_data = teams_response.json()

    temp_teams_data = []
    for division in divisions:
        division_teams = teams_reponse_data[division['id']]
        temp_teams_data.extend(division_teams)

    teams_data = temp_teams_data

    with open('teams.json', 'w') as f:
        json.dump(teams_data, f)
def get_players():
    global players_data
    print("Fetching players")

    delay = 0.1
    roster_players = []
    for team in teams_data:
        roster_players.extend(team['roster'])

    temp_players_data = []
    for player in roster_players:
        if len(temp_players_data) % 10 == 0:
            print(f'{len(temp_players_data)} of {len(roster_players)}...')

        player_uri = f"https://api2.blaseball.com/seasons/{season_id}/days/{day}/players/{player['id']}"
        player_response = requests.get(player_uri, cookies=requests.utils.cookiejar_from_dict(json.loads(os.environ.get("BB_COOKIES"))))

        player_response_data = player_response.json()
        temp_players_data.append(player_response_data)
        time.sleep(delay)

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

if __name__ == "__main__":
    set_auth_var()
    get_sim()
    get_teams()
    get_players()
    get_games()
    CORS(app)
    app.run(host='0.0.0.0', port=5000)