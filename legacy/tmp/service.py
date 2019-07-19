# -*- coding: UTF-8 -*-

import asyncio
import websockets

async def server(websocket, info):
    print("hi")
    print(info)

    '''
    CONNECTIONS[websocket]	= {
		"id"		: ID,
		"name"		: "",
		"challanger": None,			# websocket connection of the other player
		"searching"	: False,		# currently looking for a game
		"bubbling"	: False,		# prevent event bubbling if multiple requests are accidentally sent at once
		"session"	: time.time(),	# time of connection established
		"score"		: 0,			# current score
		"score_all"	: 0,			# all points gained so far
		"score_inc"	: 0,			# score received by either cooperating or defecting
		"games"		: 0,			# nubmer of games played agains opposition
		"games_all"	: 0,			# nubmer of games played total
		"choice"	: "",			# either cooperate or defect
		"duration"	: 0.0,			# time it takes to make a choice
		"environment": {},			# how the enviroment should be rendered
		"transform"	: {				# position of headset if available
			"pos"		: {
				"x"	: 0.0,
				"y"	: 0.0,
				"z"	: 0.0
			},
			"rot"		: {
				"x"	: 0.0,
				"y"	: 0.0,
				"z"	: 0.0
			}
		}
	}
	ID			+= 1
	try:
		ip	= "0.0.0.0"
		if websocket.remote_address:
			ip			= str(websocket.remote_address[0])
		log(ip+" connected ("+str(len(CONNECTIONS))+")")
		while True:
			data		= json.loads(await websocket.recv())
			# send client's headset coordinates to their opponent
			if "transform" in data and CONNECTIONS[websocket]["challanger"]:
				if "pos" in data["transform"]:
					CONNECTIONS[websocket]["transform"]["pos"]	= data["transform"]["pos"]
				if "rot" in data["transform"]:
					CONNECTIONS[websocket]["transform"]["rot"]	= data["transform"]["rot"]
				response	= {
					"type"		: "transform",
					"id"		: CONNECTIONS[websocket]["id"],
					"transform"	: CONNECTIONS[websocket]["transform"],
					"timestamp"	: time.time()
				}
				await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
			# measure duration of choices
			if "timer" in data:
				CONNECTIONS[websocket]["duration"]+= float(data["timer"])
			# prevent bubbling if multiple actions are sent
			if CONNECTIONS[websocket]["searching"] or CONNECTIONS[websocket]["bubbling"]:
				continue
			# handle actions from client
			if "action" in data:
				CONNECTIONS[websocket]["bubbling"]= True
				response	= {
					"type"		: "action",
					"message"	: "Connected.",
					"error"		: False,
					"in_game"	: False,
					"data"		: get_data(websocket),
					"timestamp"	: time.time()
				}
				if data["action"] == "ping":
					response["message"]= "pong"
					await websocket.send(json.dumps(response))
				# player provides a username
				elif data["action"] == "login":
					if not CONNECTIONS[websocket]["name"]:
						if "name" in data and data["name"]:
							log(ip+" logged in as "+str(data["name"])+" (id: "+str(CONNECTIONS[websocket]["id"])+")")
							CONNECTIONS[websocket]["name"]	= str(data["name"])
							CONNECTIONS[websocket]["score"]	= 0
						response["message"]	= "Logged in."
						response["data"]	= get_data(websocket)
						await websocket.send(json.dumps(response))
					else:
						response["message"]	= "You are already logged in."
						response["error"]	= True
						await websocket.send(json.dumps(response))
				# player looking for a match
				elif data["action"] == "search":
					if CONNECTIONS[websocket]["name"]:
						if not CONNECTIONS[websocket]["challanger"]:
							CONNECTIONS[websocket]["searching"]	= True
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
													if CONNECTIONS[socket]["searching"]:
														CONNECTIONS[socket]["searching"]	= False
														CONNECTIONS[socket]["bubbling"]		= False
														CONNECTIONS[socket]["challanger"]	= websocket
														CONNECTIONS[websocket]["challanger"]= socket
														found			= True
														break
								if found:
									break
								if not CONNECTIONS[websocket]["bubbling"]:
									break
							CONNECTIONS[websocket]["searching"]	= False
							# match found
							if found:
								GAME					+= 1
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") is challanging "+CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["name"]+" (id: "+str(CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"])+")")
								response["message"]		= "Game start."
								response["in_game"]		= True
								CONNECTIONS[websocket]["duration"]=0.0
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["duration"]=0.0
								CONNECTIONS[websocket]["score"]=0
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score"]=0
								CONNECTIONS[websocket]["games"]=0
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["games"]=0
								env						= get_game_environment()
								CONNECTIONS[websocket]["environment"]= env.copy()
								env["seat"]	= not env["seat"]
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["environment"]= env.copy()
								response["data"]		= get_data(websocket)
								await websocket.send(json.dumps(response))
								response["data"]["player"], response["data"]["opponent"] = response["data"]["opponent"], response["data"]["player"]
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
							# no match found
							elif not CONNECTIONS[websocket]["challanger"]:
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") could not find a challanger.")
								response["message"]		= "No players found."
								response["error"]		= True
								await websocket.send(json.dumps(response))
						else:
							response["message"]		= "You are already in a game session."
							response["in_game"]		= True
							response["data"]		= get_data(websocket)
							await websocket.send(json.dumps(response))
					else:
						response["message"]		= "You have to log in first."
						response["error"]		= True
						await websocket.send(json.dumps(response))
				# selecting either cooperate or defect
				elif data["action"] == "cooperate" or data["action"] == "defect":
					if CONNECTIONS[websocket]["name"]:
						if CONNECTIONS[websocket]["challanger"]:
							response["in_game"]		= True
							CONNECTIONS[websocket]["choice"]= data["action"]
							if CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"]:
								# GAME LOGIC
								CONNECTIONS[websocket]["duration"]+= CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["duration"]
								a_score, b_score		= get_game_results(CONNECTIONS[websocket]["choice"], CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"])
								CONNECTIONS[websocket]["score"]+=a_score
								CONNECTIONS[websocket]["score_all"]+=a_score
								CONNECTIONS[websocket]["score_inc"]=a_score
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score"]+=b_score
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score_all"]+=b_score
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["score_inc"]=b_score
								CONNECTIONS[websocket]["games"]+=1
								CONNECTIONS[websocket]["games_all"]+=1
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["games"]+=1
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["games_all"]+=1
								response["data"]		= get_data(websocket)
								response["message"]		= "Game set."
								await websocket.send(json.dumps(response))
								response["data"]["player"], response["data"]["opponent"] = response["data"]["opponent"], response["data"]["player"]
								await CONNECTIONS[websocket]["challanger"].send(json.dumps(response))
								CONNECTIONS[websocket]["choice"]= ""
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["choice"] = ""
								log(CONNECTIONS[websocket]["name"]+" (id: "+str(CONNECTIONS[websocket]["id"])+") VS "+CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["name"]+" (id: "+str(CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["id"])+"): "+str(a_score)+"-"+str(b_score))
								save(response)
								CONNECTIONS[websocket]["duration"]=0.0
								CONNECTIONS[CONNECTIONS[websocket]["challanger"]]["duration"]=0.0
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
			CONNECTIONS[websocket]["bubbling"]= False
	except websockets.ConnectionClosed:
		# user closes connection, close game they were in
		for socket, data in CONNECTIONS.items():
			if "challanger" in data and data["challanger"] and data["challanger"]==websocket:
				response["message"]		= "Player has disconnceted."
				response["in_game"]		= False
				response["error"]		= True
				response["data"]["opponent"]={}
				CONNECTIONS[socket]["challanger"]= None
				await socket.send(json.dumps(response))
				log("Game session was aborted due to "+ip+" disconnecting.")
		log(ip+" disconnected ("+str(len(CONNECTIONS))+")")
	finally:
		del CONNECTIONS[websocket]
	'''
