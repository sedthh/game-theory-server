import asyncio
import websockets
import json
import time
import socket
from os import path

### SETTINGS ###

IP			= "127.0.0.1" #socket.gethostbyname(socket.gethostname())
PORT		= 8765

################

CONNECTIONS	= {}
ID			= 0

async def server(websocket, path):
	global CONNECTIONS
	global ID
	CONNECTIONS[websocket]	= {
		"id"		: ID,
		"transform"	: {
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
			if "transform" in data:
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
				await websocket.send(json.dumps(response))
			elif "message" in data:
				response	= {
					"message"	: data["message"]
				}				
				await websocket.send(json.dumps(response))
	except websockets.ConnectionClosed:
		log(ip+" disconnected ("+str(len(CONNECTIONS))+")")
	finally:
		del CONNECTIONS[websocket]

def log(message):
	print(time.strftime("%H:%M:%S")+" > "+str(message))
	
if __name__ == "__main__":
	log("Server started at "+IP+":"+str(PORT))
	service = websockets.serve(server, IP, PORT)
	asyncio.get_event_loop().run_until_complete(service)
	asyncio.get_event_loop().run_forever()
	