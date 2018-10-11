# -*- coding: UTF-8 -*-

import asyncio
import websockets
import time
import codecs
import json
from numpy import random

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
	global CONNECTIONS, READY
	client_type = "UNKNOWN"
	client_ip = "0.0.0.0"
	if websocket.remote_address:
		client_ip = str(websocket.remote_address[0])
	log(f"Incoming connection: {client_ip}")
	try:
		while True:
			data = json.loads(await websocket.recv())
			response = {
				"timestamp": time.time()
			}
			# first connection
			if client_type == "UNKNOWN" and "type" in data and data["type"] in ("SUBJECT", "EXPERIMENTER"):
				client_type = data["type"]
				CONNECTIONS[client_type] = {
					"socket": websocket,		# send data from other connections here
					"session": time.time(),		# time of connection established
					"choice": "",
					"ready": False				# ready to take part in the experiment
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
							sex = random.choice([0, 1])
							response["game"] = game.get_game(SETTINGS, sex)
					elif READY:
						READY = False
						log(f"Session interrupted, {client_type} is not ready")

			# sending headset transform information
			if "transform" in data:
				if "pos" in data["transform"] and "rot" in data["transform"]:
					response["transform"] = data["transform"]
			# send message
			if "message" in data:
				response["message"] = data["message"]

			# send update to other client(s)
			for connection in CONNECTIONS:
				if connection != client_type or True:
					if CONNECTIONS[connection]["ready"]:
						await CONNECTIONS[connection]["socket"].send(json.dumps(response))

	except websockets.ConnectionClosed:
		log(f"{client_ip} ({client_type}) disconnected")
	finally:
		if client_type in CONNECTIONS:
			del CONNECTIONS[client_type]
		if READY:
			if "SUBJECT" not in CONNECTIONS or "EXPERIMENTER" not in CONNECTIONS:
				READY = False
				log(f"Session interrupted, {client_type} disconnected")

#########

if __name__ == "__main__":
	IP, PORT, LOG_FILE = game.get_settings(SETTINGS)
	CONNECTIONS = {}
	READY = False
	SESSION = 0 # make sure this increases every time
	log(f"Starting game session {SESSION}")
	log(f"Server started at {IP}:{PORT}")

	service = websockets.serve(vr_server, IP, PORT)
	asyncio.get_event_loop().run_until_complete(service)
	asyncio.get_event_loop().run_forever()
