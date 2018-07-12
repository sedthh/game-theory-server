import asyncio
import websockets
import json
import time
import numpy as np

CONNECTIONS	= {}
ID			= 0

async def server(websocket, path):
	global CONNECTIONS
	global ID
	CONNECTIONS[websocket]	= {
		"id"		: ID,
		"name"		: "",
		"challanger": None,
		"session"	: time.time(),
		"score"		: 0,
		"games"		: 0,
		"choice"	: ""
	}
	ID			+= 1
	try:
		ip	= "0.0.0.0"
		if websocket.remote_address:
			ip			= str(websocket.remote_address[0])
		log(ip+" connected ("+str(len(CONNECTIONS))+")")
		while True:
			data		= json.loads(await websocket.recv())
			response	= {
				"message"	: "Connected.",
				"error"		: False,
				"data"		: {},
				"timestamp"	: time.time()
			}
			if "action" in data:
				if data["action"] == "ping":
					response["message"]= "pong"
					await websocket.send(json.dumps(response))
				elif data["action"] == "login":
					if not CONNECTIONS[websocket]["name"]:
						if "name" in data and data["name"]:
							log(ip+" logged in as "+str(data["name"])+" (id: "+str(CONNECTIONS[websocket]["id"])+")")
							CONNECTIONS[websocket]["name"]	= str(data["name"])
							CONNECTIONS[websocket]["score"]	= 0
						response["message"]= "Logged in."
						response["data"]= {
							"id"			: CONNECTIONS[websocket]["id"],
							"players"		: len(CONNECTIONS)
						}
						await websocket.send(json.dumps(response))					
					else:
						response["message"]	= "You are already logged in."
						response["error"]	= True
						await websocket.send(json.dumps(response))	
				elif data["action"] == "search":
					if CONNECTIONS[websocket]["name"]:
						if not CONNECTIONS[websocket]["challanger"]:
							log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") is looking for a challange.")
							response["message"]	= "Searching."
							await websocket.send(json.dumps(response))
							found				= False
							for i in range(20):
								await asyncio.sleep(.25)
								for socket, data in CONNECTIONS.items():
									if socket!=websocket:
										if "id" in data and data["id"]!=CONNECTIONS[websocket]["id"]:
											if "challanger" in data and not data["challanger"]:
												if "name" in data and data["name"]:
													CONNECTIONS[socket]["challanger"]	= websocket
													CONNECTIONS[websocket]["challanger"]= socket
													found			= True
													break
								if found:
									break
							if found:
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") is challanging "+CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["name"]+" (id: "+str(CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"])+")")
								response["message"]		= "Game start."
								response["data"]		= get_game_environment()
								response["data"]["score"]= CONNECTIONS[websocket]["score"]
								response["data"]["o_score"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score"]
								response["data"]["games"]= CONNECTIONS[websocket]["games"]
								response["data"]["o_games"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["games"]								
								response["data"]["challanger"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"]
								await websocket.send(json.dumps(response))
								response["data"]["score"], response["data"]["o_score"] = response["data"]["o_score"], response["data"]["score"]
								response["data"]["games"], response["data"]["o_games"] = response["data"]["o_games"], response["data"]["games"]
								response["data"]["challanger"]= CONNECTIONS[websocket]["id"]
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
							else:
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") could not find a challanger.")
								response["message"]		= "No players found."
								response["error"]		= True
								await websocket.send(json.dumps(response))
						else:
							response["message"]		= "You are already in a game session."
							response["data"]["challanger"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"]
							await websocket.send(json.dumps(response))
					else:
						response["message"]	= "You have to log in first."
						response["error"]	= True
						await websocket.send(json.dumps(response))		
				elif data["action"] == "cooperate" or data["action"] == "defect":
					if CONNECTIONS[websocket]["name"]:
						if CONNECTIONS[websocket]["challanger"]:
							CONNECTIONS[websocket]["choice"]	= data["action"]
							if CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"]:
								# GAME LOGIC
								a_score, b_score		= get_game_results(CONNECTIONS[websocket]["choice"], CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"])
								CONNECTIONS[websocket]["score"]+=a_score
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score"]+=b_score
								CONNECTIONS[websocket]["games"]+=1
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["games"]+=1
								
								response["data"]["score"]= CONNECTIONS[websocket]["score"]
								response["data"]["o_score"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score"]
								response["data"]["choice"]= CONNECTIONS[websocket]["choice"]
								response["data"]["o_choice"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"]
								response["data"]["games"]= CONNECTIONS[websocket]["games"]
								response["data"]["o_games"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["games"]								
								response["message"]		= "Game set."
								await websocket.send(json.dumps(response))
								response["data"]["score"], response["data"]["o_score"] = response["data"]["o_score"], response["data"]["score"]
								response["data"]["choice"], response["data"]["o_choice"] = response["data"]["o_choice"], response["data"]["choice"]
								response["data"]["games"], response["data"]["o_games"] = response["data"]["o_games"], response["data"]["games"]
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
								CONNECTIONS[websocket]["choice"]= ""
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"] = ""
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") VS "+CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["name"]+" (id: "+str(CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"])+"): "+str(a_score)+"-"+str(b_score))
								# END OF GAME LOGIC
							else:
								response["message"]		= CONNECTIONS[websocket]["name"]+" has chosen."
								await websocket.send(json.dumps(response))
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
						else:
							response["message"]		= "You are not taking part in any game sessions."
							response["error"]		= True
							await websocket.send(json.dumps(response))
					else:
						response["message"]	= "You have to log in and join a game session first."
						response["error"]	= True
						await websocket.send(json.dumps(response))	
	except websockets.ConnectionClosed:
		for socket, data in CONNECTIONS.items():
			if "challanger" in data and data["challanger"] and data["challanger"]==websocket:
				response["message"]		= "Player has disconnceted."
				response["error"]		= True
				CONNECTIONS[socket]["challanger"]= None
				await socket.send(json.dumps(response))
				log("Game session was aborted due to "+ip+" disconnecting.")
		log(ip+" disconnected ("+str(len(CONNECTIONS))+")")
	finally:
		del CONNECTIONS[websocket]

def log(message):
	print(time.strftime("%H:%M:%S", time.gmtime())+" > "+str(message))
	
def get_game_environment():
	return {
		"environment"	: np.random.choice(["default","pleasant","unpleasant"]),
		"rotation"		: np.random.choice([0,90,180,270]),
	}

def get_game_results(a,b):
	a_score	= 0
	b_score	= 0
	if a=="cooperate":
		if b=="cooperate":
			a_score	= 3
			b_score	= 3
		else:
			a_score	= 0
			b_score	= 5
	else:
		if b=="cooperate":
			a_score	= 5
			b_score	= 0
		else:
			a_score	= 1
			b_score	= 1
	return a_score, b_score	
	
if __name__ == "__main__":
	log("Server started...")
	service = websockets.serve(server, 'localhost', 8765)
	asyncio.get_event_loop().run_until_complete(service)
	asyncio.get_event_loop().run_forever()