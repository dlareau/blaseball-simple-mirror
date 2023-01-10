import requests
import json
import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify

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


sched = BackgroundScheduler(daemon=True)
sched.add_job(get_games,'interval',minutes=20)
sched.start()

app = Flask(__name__)

@app.route("/games")
def show_games():
    return jsonify(game_data)

if __name__ == "__main__":
    set_auth_var()
    get_games()
    app.run(host='0.0.0.0', port=5000)