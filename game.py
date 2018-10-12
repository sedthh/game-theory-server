# -*- coding: UTF-8 -*-

import os
import configparser
from numpy import random
from sys import exit
from copy import deepcopy

STRATEGIES = ["COOPERATE", "DEFECT", "RANDOM", "TIT-FOR-TAT", "ALTERNATING"]
STRATEGY = "RANDOM"
SUBJECT_CHOICES = []
EXPERIMENTER_CHOICES = []
AIS = []
ENVIRONMENTS = []
MAX_GAMES_VR = 0
MAX_GAMES_BEFORE = 0
MAX_GAMES_AFTER = 0

def shuffle(my_list,expand=True):
	if my_list:
		output_list = []
		while len(output_list) < MAX_GAMES_VR:
			random.shuffle(my_list)
			output_list += my_list
			if not expand:
				break
		return output_list[:MAX_GAMES_VR]

def get_settings(file):
	global MAX_GAMES_VR
	config = os.path.join(os.path.dirname(os.path.realpath(__file__)), file)
	if os.path.isfile(config):
		settings = configparser.ConfigParser()
		settings.read(config)
		if "SERVER" in settings:
			try:
				ip = settings["SERVER"]["IP"]
				port = int(settings["SERVER"]["PORT"])
				log_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), settings["SERVER"]["LOG_FILE"])
				wait = settings["SERVER"]["WAIT"]
				games = int(settings["SERVER"]["MAX_GAMES_BEFORE"]) + int(settings["SERVER"]["MAX_GAMES_VR"]) + int(settings["SERVER"]["MAX_GAMES_AFTER"])
				get_data(file)
				return ip, port, log_file, wait, games
			except KeyError as error:
				exit(f"Configuration file missing argument: {str(error)}")
	exit(f"Missing or malformed configuration file: {file}")

def get_data(file):
	global AIS, ENVIRONMENTS, MAX_GAMES_VR, MAX_GAMES_BEFORE, MAX_GAMES_AFTER
	config = os.path.join(os.path.dirname(os.path.realpath(__file__)), file)
	if os.path.isfile(config):
		settings = configparser.ConfigParser()
		settings.read(config)
		MAX_GAMES_VR = int(settings["SERVER"]["MAX_GAMES_VR"])
		MAX_GAMES_BEFORE = int(settings["SERVER"]["MAX_GAMES_BEFORE"])
		MAX_GAMES_AFTER = int(settings["SERVER"]["MAX_GAMES_AFTER"])

		males = {
			"names": shuffle([key for key in settings["NAMES"] if int(settings["NAMES"][key]) == 1], False),
			"avatars": shuffle([key for key in settings["AVATARS"] if int(settings["AVATARS"][key]) == 1], False)
		}
		females = {
			"names": shuffle([key for key in settings["NAMES"] if int(settings["NAMES"][key]) == 0], False),
			"avatars": shuffle([key for key in settings["AVATARS"] if int(settings["AVATARS"][key]) == 0], False)
		}

		AIS += zip(males["names"],males["avatars"])
		AIS += zip(females["names"], females["avatars"])
		AIS = [("", "") for i in range(MAX_GAMES_BEFORE)] + shuffle(AIS) + [("", "") for i in range(MAX_GAMES_AFTER)]
		ENVIRONMENTS = shuffle([settings["ENVIRONMENTS"][key] for key in settings["ENVIRONMENTS"]])
		ENVIRONMENTS = ["" for i in range(MAX_GAMES_BEFORE)] + ENVIRONMENTS + ["" for i in range(MAX_GAMES_AFTER)]

def get_name(game):
	return AIS[game][0]

def get_avatar(game):
	return AIS[game][1]

def get_environment(game):
	return ENVIRONMENTS[game]

def get_strategy():
	return random.choice(STRATEGIES)

def get_game(game=0):
	global STRATEGY
	response = {
		"name": get_name(game),
		"avatar": get_avatar(game),
		"environment": get_environment(game),
		"rotation": random.randint(0, 360)
	}
	STRATEGY = get_strategy()
	return response

def get_test(subject, experimenter, game=0):
	game_data = get_game(game)
	subject["data"]["environment"] = game_data["environment"]
	experimenter["data"]["environment"] = game_data["environment"]
	subject["data"]["rotation"] = game_data["rotation"]
	experimenter["data"]["rotation"] = (game_data["rotation"]+180)%360
	experimenter["data"]["name"] = game_data["name"]
	experimenter["data"]["avatar"] = game_data["avatar"]
	loading = int(random.choice([1, 2, 3]))
	subject["data"]["loading"] = loading
	experimenter["data"]["loading"] = loading
	subject["data"]["message"] = "Searching for match."
	experimenter["data"]["message"] = "Searching for match."
	rounds_to_play = random.randint(3, 8)
	subject["data"]["game"]["rounds_left"] = rounds_to_play
	experimenter["data"]["game"]["rounds_left"] = rounds_to_play
	subject["data"]["choice"] = ""
	experimenter["data"]["choice"] = ""
	return subject, experimenter

def play_once(subject, experimenter):
	global SUBJECT_CHOICES, EXPERIMENTER_CHOICES
	SUBJECT_CHOICES.append(subject["data"]["choice"])
	EXPERIMENTER_CHOICES.append(experimenter["data"]["choice"])

	subject_score, experimenter_score = get_game_results(subject["data"]["choice"], experimenter["data"]["choice"])
	game = {
		"rounds_left": max(subject["data"]["game"]["rounds_left"],experimenter["data"]["game"]["rounds_left"])-1,
		"SUBJECT": {
			"choice": subject["data"]["choice"],
			"score": subject["data"]["game"]["SUBJECT"]["score"]+subject_score,
			"score_all": subject["data"]["game"]["SUBJECT"]["score_all"]+subject_score
		},
		"EXPERIMENTER": {
			"choice": experimenter["data"]["choice"],
			"score": experimenter["data"]["game"]["EXPERIMENTER"]["score"] + experimenter_score,
			"score_all": experimenter["data"]["game"]["EXPERIMENTER"]["score_all"] + experimenter_score
		}
	}
	subject["data"]["choice"] = ""
	experimenter["data"]["choice"] = ""
	subject["data"]["game"] = deepcopy(game)
	experimenter["data"]["game"] = deepcopy(game)
	return subject, experimenter

def get_game_results(a, b):
	# payoff matrix
	if a == "cooperate":
		if b == "cooperate":
			a_score = 3
			b_score = 3
		else:
			a_score = 0
			b_score = 5
	else:
		if b == "cooperate":
			a_score = 5
			b_score = 0
		else:
			a_score = 1
			b_score = 1
	return a_score, b_score

def get_choice():
	if STRATEGY == "COOPERATE":
		return "cooperate"
	elif STRATEGY == "DEFECT":
		return "defect"
	elif STRATEGY == "TIT-FOR-TAT":
		if SUBJECT_CHOICES:
			return SUBJECT_CHOICES[-1]
		else:
			return "cooperate"
	elif STRATEGY == "ALTERNATING":
		if EXPERIMENTER_CHOICES:
			if EXPERIMENTER_CHOICES[-1] == "cooperate":
				return "defect"
			else:
				return "cooperate"
		else:
			return "cooperate"
	else:
		return random.choice(["cooperate", "defect"])

if __name__ == "__main__":
	_,_,_,_,_ =get_settings("settings.ini")
	for i in range(MAX_GAMES_VR+2):
		print(get_game(i))