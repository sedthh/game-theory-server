# -*- coding: UTF-8 -*-

import asyncio
import websockets
import time
import codecs
import json
from copy import deepcopy

import game
SETTINGS = "settings.ini"

def log(message):
	global LOG_FILE
	print(time.strftime("%H:%M:%S") + " > " + str(message))
	f = codecs.open(LOG_FILE, "a+", encoding="utf-8")
	f.write(time.strftime('%Y-%m-%d %H:%M:%S') + "\t" + str(message))
	f.write("\r\n")
	f.close()

##########

async def vr_server(websocket, path):
	global CONNECTIONS, READY, GAMES_PLAYED, LOCK
	client_type = "UNKNOWN"
	client_ip = "0.0.0.0"
	last_update = time.time()
	if websocket.remote_address:
		client_ip = str(websocket.remote_address[0])
	log(f"Incoming connection: {client_ip}")
	try:
		while True:
			data = json.loads(await websocket.recv())
			# first connection
			if client_type == "UNKNOWN" and "type" in data and data["type"] in ("SUBJECT", "EXPERIMENTER"):
				client_type = data["type"]
				if client_type in CONNECTIONS:
					CONNECTIONS[client_type]["socket"].append(websocket)
				else:
					CONNECTIONS[client_type] = {
						"socket": [websocket],		# send data from other connections here
						"session": time.time(),		# time of connection established
						"ready": False,  			# ready to take part in the experiment
						"data": {
							"timestamp": 0,				# current timestamp (gets updated)
							"name": "Unknown",
							"avatar": "default",
							"environment": "default",	# current environment
							"rotation": 0,				# rotation of environment
							"loading": 0,				# show fake loading for this long
							"message": "Connected.",	# messages for debugging
							"choice": "",				# the last sent choice (["game"]["me"]["choice"] will also have its value)
							"is_vr": False,				# is current game session a VR session
							"is_over": False,			# is game session over
							"game": {
								"rounds_left": 0,
								"SUBJECT": {
									"choice": "",
									"score": 0,
									"score_all": 0
								},
								"EXPERIMENTER": {
									"choice": "",
									"score": 0,
									"score_all": 0
								}
							},
							"transform": {				# position and rotation of headset
								"pos": {
									"x": 0.0,
									"y": 0.0,
									"z": 0.0
								},
								"rot": {
									"x": 0.0,
									"y": 0.0,
									"z": 0.0
								}
							}
						}
					}
				log(f"{client_ip} is identified as {client_type}")

			# connection is ready
			if "ready" in data and client_type in CONNECTIONS:
				CONNECTIONS[client_type]["ready"] = bool(data["ready"])
				if "SUBJECT" in CONNECTIONS and "EXPERIMENTER" in CONNECTIONS:
					if CONNECTIONS["SUBJECT"]["ready"] and CONNECTIONS["EXPERIMENTER"]["ready"]:
						if not READY:
							READY = True
							log(f"Both subject and experimenter have joined the session")
							CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"] = \
								game.get_test(CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"], GAMES_PLAYED)
							await send_all()
					elif READY:
						READY = False
						log(f"Session interrupted, {client_type} is not ready")

			# subject sets name (just save it for later)
			if "name" in data and client_type in CONNECTIONS and data["name"]:
				CONNECTIONS[client_type]["data"]["name"] = data["name"]

			# subject sets avatar (just save it for later)
			if "avatar" in data and client_type in CONNECTIONS and data["avatar"]:
				CONNECTIONS[client_type]["data"]["avatar"] = data["avatar"]

			# sending headset transform information when received
			if "transform" in data and client_type in CONNECTIONS:
				if "pos" in data["transform"] and "rot" in data["transform"]:
					# update the headset rotation and send it to others
					if time.time() > last_update + FPS:
						await send(client_type, {"transform": data["transform"]})
						last_update = time.time()

			# subject sends their choice
			if "choice" in data and data["choice"] in ("cooperate", "defect") and client_type in CONNECTIONS:
				if not LOCK:
					if GAMES_PLAYED < MAX_GAMES:
						if READY:
							# play the game
							if client_type == "SUBJECT":
								# subject plays the game
								CONNECTIONS[client_type]["data"]["choice"] = data["choice"]
							elif client_type == "EXPERIMENTER":
								# discard choice and get actual choice from game AI based on selected strategy
								CONNECTIONS[client_type]["data"]["choice"] = game.get_choice()
							# calculate results if both players have chosen
							if "SUBJECT" in CONNECTIONS and "EXPERIMENTER" in CONNECTIONS:
								if CONNECTIONS["SUBJECT"]["data"]["game"]["rounds_left"] > 0:
									if CONNECTIONS["SUBJECT"]["data"]["choice"] and CONNECTIONS["EXPERIMENTER"]["data"]["choice"]:
										log(f'Game played: {CONNECTIONS["SUBJECT"]["data"]["choice"]} - ' \
											f'{CONNECTIONS["EXPERIMENTER"]["data"]["choice"]}')
										CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"] = \
											game.play_once(CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"])
										await send_all()
										# TODO: save events
										LOCK = True
										await asyncio.sleep(WAIT)

								# generate new test or end session
								if CONNECTIONS["SUBJECT"]["data"]["game"]["rounds_left"] <= 0:
									GAMES_PLAYED += 1
									if GAMES_PLAYED >= MAX_GAMES:
										CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"] = \
											game.end_test(CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"])
										await send_all()
										log(f'This session is over, all tests have been played.')
									else:
										CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"] = \
											game.get_test(CONNECTIONS["SUBJECT"], CONNECTIONS["EXPERIMENTER"], GAMES_PLAYED)
										await send_all()
										log(f'Generating #{(GAMES_PLAYED+1)} game')
										LOCK = True
										await asyncio.sleep(CONNECTIONS["SUBJECT"]["data"]["loading"])
						else:
							await echo(client_type, {"message": "You are not in a match yet."})
					else:
						await echo(client_type, {"message": "Your game session is over."})
				else:
					await echo(client_type, {"message": "Please wait a bit until sending in your next choice."})
				LOCK = False

	except websockets.ConnectionClosed:
		log(f"{client_ip} ({client_type}) disconnected")
	finally:
		if client_type in CONNECTIONS:
			CONNECTIONS[client_type]["socket"] = \
				[socket for socket in CONNECTIONS[client_type]["socket"] if socket != websocket]
			if not CONNECTIONS[client_type]["socket"]:
				del CONNECTIONS[client_type]
		if READY:
			if "SUBJECT" not in CONNECTIONS or "EXPERIMENTER" not in CONNECTIONS:
				READY = False
				log(f"Session interrupted, {client_type} disconnected")

# send certain data (update sender's data with new data) and send it to everyone else but the sender
async def send(sender,data):
	global CONNECTIONS
	if sender in CONNECTIONS:
		if CONNECTIONS[sender]["ready"]:
			# update sender's data
			CONNECTIONS[sender]["data"]["timestamp"] = time.time()
			for key in data:
				if key in CONNECTIONS[sender]["data"]:
					CONNECTIONS[sender]["data"][key] = data[key]
			data["timestamp"] = CONNECTIONS[sender]["data"]["timestamp"]
			data["games_played"] = GAMES_PLAYED
			message = json.dumps(data)
			# send to others
			for recipient in CONNECTIONS:
				if sender != recipient:
					if CONNECTIONS[recipient]["ready"]:
						for socket in CONNECTIONS[recipient]["socket"]:
							await socket.send(message)

# update sender's data and send it back to it
async def echo(sender,data):
	global CONNECTIONS
	if sender in CONNECTIONS:
		CONNECTIONS[sender]["data"]["timestamp"] = time.time()
		for key in data:
			if key in CONNECTIONS[sender]["data"]:
				CONNECTIONS[sender]["data"][key] = data[key]
		data["timestamp"] = CONNECTIONS[sender]["data"]["timestamp"]
		data["games_played"] = GAMES_PLAYED
		message = json.dumps(data)
		for socket in CONNECTIONS[sender]["socket"]:
			await socket.send(message)

# send everything to everyone
async def send_all():
	for sender in CONNECTIONS:
		if CONNECTIONS[sender]["ready"]:
			CONNECTIONS[sender]["data"]["timestamp"] = time.time()
			data = deepcopy(CONNECTIONS[sender]["data"])
			data["games_played"] = GAMES_PLAYED
			message = json.dumps(data)
			for recipient in CONNECTIONS:
				if sender != recipient:
					if CONNECTIONS[recipient]["ready"]:
						for socket in CONNECTIONS[recipient]["socket"]:
							await socket.send(message)
			CONNECTIONS[sender]["data"]["loading"] = 0

#########

if __name__ == "__main__":
	IP, PORT, LOG_FILE, WAIT, MAX_GAMES, FPS = game.get_settings(SETTINGS)
	CONNECTIONS = {}
	READY = False
	LOCK = False
	GAMES_PLAYED = 0
	SESSION = 0 # make sure this increases every time
	log(f"Starting game session {SESSION}")
	log(f"Server started at {IP}:{PORT}")

	service = websockets.serve(vr_server, IP, PORT)
	asyncio.get_event_loop().run_until_complete(service)
	asyncio.get_event_loop().run_forever()
