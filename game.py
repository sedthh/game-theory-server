# -*- coding: UTF-8 -*-

import os
import configparser
from numpy import random
from sys import exit

STRATEGIES = ["COOPERATE", "DEFECT", "RANDOM", "TIT-FOR-TAT", "ALTERNATING"]
STRATEGY = "RANDOM"

def get_settings(file):
	config = os.path.join(os.path.dirname(os.path.realpath(__file__)), file)
	if os.path.isfile(config):
		settings = configparser.ConfigParser()
		settings.read(config)
		if "SERVER" in settings:
			try:
				ip = settings["SERVER"]["IP"]
				port = int(settings["SERVER"]["PORT"])
				log_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), settings["SERVER"]["LOG_FILE"])
				return ip, port, log_file
			except KeyError as error:
				exit(f"Configuration file missing argument: {str(error)}")
	exit(f"Missing or malformed configuration file: {file}")

def get_name(file,sex=0):
	return get_data(file,"NAMES",sex)

def get_avatar(file,sex=0):
	return get_data(file, "AVATARS", sex)

def get_data(file,section,value):
	config = os.path.join(os.path.dirname(os.path.realpath(__file__)), file)
	if os.path.isfile(config):
		settings = configparser.ConfigParser()
		settings.read(config)
		if section in settings:
			choices = [name for name in settings[section] if int(settings[section][name]) == value]
			if choices:
				return random.choice(choices)
	raise Exception("Could not find data with value={value} in {section}")

def get_strategy():
	return random.choice(STRATEGIES)

def get_game(file,sex):
	global STRATEGY
	response = {
		"name": get_name(file, sex),
		"avatar": get_avatar(file, sex)
	}
	STRATEGY = get_strategy()
	return response
