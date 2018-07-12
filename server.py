import asyncio
import websockets
import json
import time

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
								response["data"]["challanger"]= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"]
								await websocket.send(json.dumps(response))
								response["data"]["challanger"]= CONNECTIONS[websocket]["id"]
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
							else:
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") could not find a challanger.")
								response["message"]		= "No players found."
								response["error"]		= True
								await websocket.send(json.dumps(response))
						else:
							log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") is already in a game.")
							response["message"]		= "Game continues."
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
								# TODO: implement game logic
								response["message"]		= "Game set."
								await websocket.send(json.dumps(response))
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
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
		
if __name__ == "__main__":
	log("Server started...")
	service = websockets.serve(server, 'localhost', 8765)
	asyncio.get_event_loop().run_until_complete(service)
	asyncio.get_event_loop().run_forever()