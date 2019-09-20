#!/usr/bin/env python

import time
import json
import asyncio
import websockets
import atexit
from socket import gethostbyname, gethostname


class Server:

		DEFAULT_ROOM = "lobby"
		DEFAULT_HISTORY = 50

		def __init__(self, ip="", port=42069, fps=1, log_level=3):
			self.ip = ip if ip else gethostbyname(gethostname())
			self.port = port
			self.frequency = 1.0/fps
			self.log_level = max(0, log_level)

			self.rooms = {}
			self.open(self.DEFAULT_ROOM)
			self.users = {}
			self.loop = asyncio.get_event_loop()
			asyncio.set_event_loop(self.loop)
			self.service = None
			self.tasks = []

		# start server
		def run(self):
			self.service = websockets.serve(self._connection, self.ip, self.port)
			self.tasks = [asyncio.ensure_future(self.service), asyncio.ensure_future(self.tic())]
			self.log(f"Server starting at {self.ip}:{self.port}")
			try:
				self.loop.run_until_complete(asyncio.gather(*self.tasks))
				self.loop.run_forever()
			except KeyboardInterrupt:
				self.stop()

		@atexit.register
		def stop(self):
			self.log("Closing server.")
			self.service.ws_server.close()
			self.service.ws_server.wait_closed()
			asyncio.gather(*asyncio.Task.all_tasks()).cancel()
			self.loop.close()
			self.loop = None

		# send out headset orientation on tics
		async def tic(self):
			current = time.time()
			while True:
				if current + self.frequency < time.time():
					current = time.time()
					await self.headsets()
				await asyncio.sleep(self.frequency/10.0)

		def log(self, con, msg=None, level=0):
			if level <= self.log_level:
				if msg is None:
					con, msg = "", con
				print(f'{time.strftime("%H:%M:%S")} > {con}{msg}')

		@staticmethod
		def _validate_in(payload):
			result = {}
			for must in ("room", "data"):
				if must not in payload:
					raise KeyError(f"payload missing key {must}")
				result[must] = payload[must]
			result["type"] = payload["type"] if "type" in payload else "msg"
			result["time"] = payload["time"] if "time" in payload else time.time()
			return result

		@staticmethod
		def _validate_out(payload):
			return {
				"time": payload["time"] if "time" in payload else time.time(),
				"user": payload["user"] if "user" in payload else "",
				"type": payload["type"] if "type" in payload else "msg",
				"data": payload["data"] if "data" in payload else ""
			}

		@staticmethod
		def _validate_transform(payload):
			if "data" not in payload:
				payload["data"] = {}
			for key in ("pos", "rot"):
				if key not in payload["data"]:
					payload["data"][key] = {}
				for cord in ("x", "y", "z"):
					if cord not in payload["data"][key]:
						payload["data"][key][cord] = 0
			return {key: payload["data"][key].copy() for key in ("pos", "rot")}

		@staticmethod
		def _get_system_message(code):
			# msg
			if code == 200:
				return "Ok." # may be overwritten
			elif code == 202:
				return "Access granted."
			elif code == 212:
				return "Listing information."
			elif code == 214:
				return "Help message." # TODO: add info
			elif code == 220:
				return "Pong."
			# error
			elif code == 400:
				return "Bad request."
			elif code == 401:
				return "User unauthorized."
			elif code == 403:
				return "Access denied."
			elif code == 406:
				return "Data object has invalid structure."
			elif code == 409:
				return "Request conflicts current status."
			elif code == 500:
				return "Internal server error."
			elif code == 501:
				return "Command not recognized."
			return "Unknown."

		def id(self, user):
			if not self.users[user]["nick"]:
				return f'{self.users[user]["ip"]} '
			return f'{self.users[user]["nick"]} ({self.users[user]["ip"]}) '

		async def _connection(self, user, path):
			# connect user
			self.connect(user)
			self.log(self.id(user), 'trying to connect', 1)
			try:
				# wait for data from user once the connection is established
				while True:
					try:
						self.users[user]["updated"] = time.time()
						message = json.loads(await user.recv())

						if "system" in message:
							# system commands
							# log in with credentials
							if message["system"] == "login":
								# TODO: do actual authentication later
								if "user" in message["options"] and "pass" in message["options"]:
									self.users[user]["nick"] = message["options"]["user"]
									self.users[user]["auth"] = True
									self.log(self.id(user), 'logged in', 1)
									await self.system(user, 202)
									# await self.system(user, 400)
									await self.join(user, self.DEFAULT_ROOM)
								else:
									await self.system(user, 400)
							elif message["system"] == "ping":
								await self.system(user, 220)

							# system messages that require auth
							elif self.users[user]["auth"]:
								if message["system"] == "rooms":
									await self.list_rooms(user)
								else:
									# not implemented
									await self.system(user, 501)
							else:
								# not autherized
								await self.system(user, 403)

						# non system messages, that all require auth
						elif self.users[user]["auth"]:
							# check payload after auth
							try:
								message = self._validate_in(message)
							except KeyError as e:
								await self.system(user, 400)
								self.log(self.id(user), 'sent invalid data', 1)
								continue

							# in room
							if self.in_room(user, message["room"]):
								if message["type"] == "transform":
									self.rooms[message["room"]]["users"][user]["transform"] = self._validate_transform(message)
								elif message["type"] == "join":
									# already in room
									await self.system(user, 409)
								elif message["type"] == "leave":
									await self.leave(user, message["room"])
								elif message["type"] == "list":
									await self.list_users(user, message["room"])
								else:
									# otherwise save the data to history and broadcast it
									payload = self._validate_out({"user": self.users[user]["nick"], **message})
									self.history(message["room"], payload)
									await self.broadcast(message["room"], payload)
							# not in room
							else:
								if message["type"] == "join":
									await self.join(user, message["room"])
								else:
									# need to join room first
									await self.system(user, 401)
						else:
							await self.system(user, 403)

					except json.decoder.JSONDecodeError:
						await self.system(user, 406)
						self.log(self.id(user), 'sent malformed JSON', 1)
						continue

			# disconnect user
			except websockets.ConnectionClosed:
				self.log(self.id(user), 'disconnected')
			except websockets.WebSocketProtocolError:
				self.log(self.id(user), 'broke protocol')
			except websockets.PayloadTooBig:
				self.log(self.id(user), 'sent payload that is too large')
			except Exception as e:
				self.log(self.id(user), f'caused unknown exception: {e}')
			finally:
				try:
					await self.disconnect(user)
				except Exception as e:
					del self.users[user]
					self.log(f'Failed to safely disconnect: {e}')

		# create user data when connection is established
		def connect(self, user, data={}):
			if user in self.users:
				return
			default = {
				"auth": False,
				"nick": "",
				"level": "user",
				"status": "online",
				"connected": time.time(),
				"updated": time.time(),
				"ip": (user.remote_address[0] if user.remote_address else "0.0.0.0"),
				"rooms": set(),
				"meta": {},
			}
			self.users[user] = {**default, **data}

		# remove user data when connection is closed
		async def disconnect(self, user):
			if user in self.users:
				for room in self.users[user]["rooms"].copy():
					await self.leave(user, room)
				del self.users[user]

		# open a new room
		def open(self, room, payload={}):
			if room in self.rooms:
				return
			default = {
				"title": "",
				"created": time.time(),
				"users": {},
				"history": [],
				"size": self.DEFAULT_HISTORY
			}
			self.rooms[room] = {**default, **payload}

		def _room_user(self, user):
			return {
				"nick": self.users[user]["nick"],
				"transform": {
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

		# close an existing room
		async def close(self, room):
			if room == self.DEFAULT_ROOM:
				return
			if room in self.rooms:
				for user in self.users:
					await self.leave(user, room, True)

		# join an existing room
		async def join(self, user, room):
			if room and user in self.users and self.users[user]["auth"]:
				if room not in self.rooms:
					self.open(room)
				self.users[user]["rooms"].add(room)
				self.rooms[room]["users"][user] = self._room_user(user)
				# send history to user
				await self.list_users(user, room)
				history = self.history(room)
				if history:
					await self.send(user, room, history)

				# broadcast join event for everyone but the user
				await self.broadcast(room, [{"user": self.users[user]["nick"], "type": "join", "data": ""}], ignore=user)
				self.log(self.id(user), f'joined "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
			else:
				self.log(self.id(user), f'failed to join "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
				await self.system(user, 401)

		async def leave(self, user, room, force=False):
			if room and user in self.users and room in self.rooms:
				await self.broadcast(room, [{"user": self.users[user]["nick"], "type": "leave", "data": ""}], ignore=(None if force else user))
				self.users[user]["rooms"].discard(room)
				del self.rooms[room]["users"][user]

				if len(self.rooms[room]["users"]) == 0:
					if room != self.DEFAULT_ROOM:
						del self.rooms[room]
				self.log(self.id(user), f'left "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
			else:
				self.log(self.id(user), f'failed to leave "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
				await self.system(user, 401)

		async def list_users(self, user, room):
			if room and user in self.users and room in self.rooms:
				nicks = sorted([self.rooms[room]["users"][con]["nick"] for con in self.rooms[room]["users"]], key=str.lower)
				await self.send(user, room, [{"user": nick, "type": "join", "data": ""} for nick in nicks])
			else:
				self.log(self.id(user), f'failed to list users in "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
				await self.system(user, 401)

		async def list_rooms(self, user):
			if user in self.users:
				#rooms = sorted([room for room in self.rooms], key=str.lower)
				detail = {room: self.rooms[room]["title"] for room in self.rooms}
				await self.system(user, 212, "", detail)
			else:
				self.log(self.id(user), f'failed to list rooms', 2)
				await self.system(user, 401)

		def in_room(self, user, room):
			if user in self.users:
				if room in self.rooms:
					return user in self.rooms[room]["users"]
			return False

		### handle sending messages

		def _create_payload(self, room, payload, check=True):
			if type(payload) is not list:
				payload = [payload]
			return {
				"info": "user",
				"room": room,
				"payload": [self._validate_out(p) if check else p for p in payload]
			}

		# send payload as it is to user through websocket connection
		async def post(self, user, message):
			try:
				if user in self.users:
					await user.send(json.dumps(message))
			except Exception as e:
				self.log(f"Unable to send to {self.id(user)}: {e}", 1)

		# extend and send payload to a single user in a room
		async def send(self, user, room, payload):
			if room in self.rooms and user in self.users:
				await self.post(user, self._create_payload(room, payload))

		# send system message to user on error
		async def system(self, user, code=200, msg="", detail={}):
			if user in self.users:
				payload = {
					"info": ("system" if (code >= 100 and code < 400) else "error"),
					"response": {
						"time": time.time(),
						"code": code,
						"msg": (msg if msg else self._get_system_message(code)),
						"detail": detail
					}
				}
				await self.post(user, payload)

		# extend and send payload to all users in a room (except selected one)
		async def broadcast(self, room, payload, ignore=None):
			if room in self.rooms:
				message = self._create_payload(room, payload)
				for recipient in self.rooms[room]["users"]:
					if recipient in self.users and self.users[recipient]["auth"] and recipient != ignore:
						await self.post(recipient, message)

		# send all headset data to all rooms
		async def headsets(self):
			for room in self.rooms:
				all_transforms = []
				for recipient in self.rooms[room]["users"]:
					all_transforms.append({
						"user": self.rooms[room]["users"][recipient]["nick"],
						"type": "transform",
						"data": self.rooms[room]["users"][recipient]["transform"]
					})
				if all_transforms:
					await self.broadcast(room, all_transforms)

		def history(self, room, payload=None):
			if room in self.rooms:
				if payload is not None:
					self.rooms[room]["history"].append(payload)
					self.rooms[room]["history"] = self.rooms[room]["history"][-self.rooms[room]["size"]:]
				return self.rooms[room]["history"]
			else:
				return []

if __name__ == "__main__":
	server = Server()
	server.run()
