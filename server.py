#!/usr/bin/env python

import codecs
import json
import asyncio
import websockets
import atexit
from socket import gethostbyname, gethostname
from datetime import datetime


class Server:

		DEFAULT_ROOM = "lobby"
		JOIN_DEFAULT_ROOM = True
		ALLOW_MULTIPLE_ROOMS = True
		DEFAULT_HISTORY = 50

		def __init__(self, ip="", port=42069, fps=1, log_level=3, log_file=""):
			''' Init Server class. Will run on local IP:42069 by default.

			Headset information will be broadcasted depending on the value of "fps",
			sending it more frequently from the client side will have no effect.
			fps = 10  # resend headset transformation 10 times in a second

			'''

			self.ip = ip if ip else gethostbyname(gethostname())
			self.port = port
			self.frequency = 1.0 / fps
			self.log_level = max(0, log_level)
			self.log_file = log_file

			self.rooms = {}
			self.open(self.DEFAULT_ROOM)
			self.users = {}
			self.loop = asyncio.get_event_loop()
			asyncio.set_event_loop(self.loop)
			self.service = None
			self.tasks = []

			if self.log_file:
				self.log(f"Server will save event to file \"{self.log_file}\"")
			else:
				self.log(f"Server will not save events to file.")

		@staticmethod
		def now(f=""):
			''' Return current timestamp with microseconds, format it as string if "f" is set '''
			if not f:
				return datetime.timestamp(datetime.now())
			else:
				return datetime.now().strftime(f)

		# start server
		def run(self):
			''' Run server based on class information '''
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
			''' Stop server (hopefully called when closing application) '''
			self.log("Closing server.")
			self.service.ws_server.close()
			self.service.ws_server.wait_closed()
			asyncio.gather(*asyncio.Task.all_tasks()).cancel()
			self.loop.close()
			self.loop = None

		# send out headset orientation on tics
		async def tic(self):
			''' Generate tics in background to send headset information async '''
			current = self.now()
			while True:
				if current + self.frequency < self.now():
					current = self.now()
					await self.headsets()
				await asyncio.sleep(self.frequency/10.0)

		def log(self, con, msg=None, level=0):
			''' Print server messages based on log level '''
			if level <= self.log_level:
				if msg is None:
					con, msg = "", con
				print(f'{self.now("%H:%M:%S")} > {con}{msg}')

		def dump(self, user, room, action, message):
			''' Save relevant user events to CSV file '''
			if self.log_file and user in self.users:
				try:
					f = codecs.open(self.log_file, "a+", encoding="utf-8")
				except Exception as e:
					self.log(e)
					return
				ip = self.users[user]["ip"]
				nick = "" if not self.users[user]["nick"] else self.users[user]["nick"]
				timestamp = self.now("%Y-%m-%d %H:%M:%S.%f")  # microseconds
				if type(message) not in (str, int, float):
					message = json.dumps(message)
				f.write(f"{timestamp};{ip};{nick.replace(';', ',')};{room.replace(';', ',')};{action.replace(';', ',')};{message.replace(';', ',')};\r\n")
				f.close()

		@staticmethod
		def _validate_in(payload):
			''' Ensure that received payload from client is valid '''
			result = {}
			for must in ("room", "data"):
				if must not in payload:
					raise KeyError(f"payload missing key {must}")
				result[must] = payload[must]
			result["type"] = payload["type"] if "type" in payload else "msg"
			result["time"] = payload["time"] if "time" in payload else Server.now()
			return result

		@staticmethod
		def _validate_out(payload):
			''' Ensure that payload is valid when sending it to clients '''
			return {
				"time": payload["time"] if "time" in payload else Server.now(),
				"user": payload["user"] if "user" in payload else "",
				"type": payload["type"] if "type" in payload else "msg",
				"data": payload["data"] if "data" in payload else ""
			}

		@staticmethod
		def _validate_transform(payload):
			''' Ensure that payload is valid for sending headset transformation data '''
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
			''' Return system codes similar to HTTP / FTP status (200-300 ok, 400-500 error) '''
			# ok
			if code == 200:
				return "Ok."  # may be overwritten
			elif code == 202:
				return "Access granted."
			elif code == 212:
				return "Listing information."
			elif code == 214:
				return "Help message."  # TODO: add info
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
			''' Return user's "ip" or "nick (ip)" if nick is set '''
			if user not in self.users:
				return f'{user}'
			if not self.users[user]["nick"]:
				return f'{self.users[user]["ip"]} '
			return f'{self.users[user]["nick"]} ({self.users[user]["ip"]}) '

		async def _connection(self, user, path):
			''' Handle all incoming connections and messages from clients '''
			self.connect(user)  # connect user
			self.log(self.id(user), 'trying to connect', 1)
			try:
				# wait for data from user once the connection is established
				while True:
					try:
						self.users[user]["updated"] = self.now()
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
									if self.JOIN_DEFAULT_ROOM:
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
								# not authorized
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
								elif message["type"] == "button":
									# same as msg but does not save it to history
									payload = self._validate_out({"user": self.users[user]["nick"], **message})
									self.dump(user, message["room"], message["type"], message["data"])
									await self.broadcast(message["room"], payload)
								else:
									# otherwise save the data to history and broadcast it
									payload = self._validate_out({"user": self.users[user]["nick"], **message})
									self.history(message["room"], payload)
									self.dump(user, message["room"], message["type"], message["data"])
									await self.broadcast(message["room"], payload)
							# not in room
							else:
								if message["type"] == "join":
									if self.ALLOW_MULTIPLE_ROOMS:
										await self.join(user, message["room"])
									else:
										await self.switch(user, message["room"])
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
					self.log(self.id(user), f'failed to safely disconnect from: {e}')
					del self.users[user]

		def connect(self, user, data={}):
			''' Create user data when connection is established '''
			if user in self.users:
				return
			default = {
				"auth": False,
				"nick": "",
				"level": "user",
				"status": "online",
				"connected": self.now(),
				"updated": self.now(),
				"ip": (user.remote_address[0] if user.remote_address else "0.0.0.0"),
				"rooms": set(),
				"meta": {},
			}
			self.users[user] = {**default, **data}

		async def disconnect(self, user):
			''' Remove user data when connection is closed '''
			if user in self.users:
				for room in self.users[user]["rooms"].copy():
					await self.leave(user, room)
				del self.users[user]

		def open(self, room, payload={}):
			''' Open a new room '''
			if room in self.rooms:
				return
			default = {
				"title": "",
				"created": self.now(),
				"users": {},
				"history": [],
				"size": self.DEFAULT_HISTORY
			}
			self.rooms[room] = {**default, **payload}

		def _room_user(self, user):
			''' Generate cache of user for a room '''
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

		async def close(self, room):
			''' Close a room, force users joined to leave '''
			if room == self.DEFAULT_ROOM:
				return
			if room in self.rooms:
				for user in self.users:
					await self.leave(user, room, True)

		async def join(self, user, room):
			''' Join a room, open room if not available '''
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
				self.dump(user, room, "join", "")
			else:
				self.log(self.id(user), f'failed to join "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
				await self.system(user, 401)

		async def leave(self, user, room, force=False):
			''' Leave a room, close room if empty, except if it's the default lobby '''
			if not user or not room:
				return
			await self.broadcast(room, [{"user": self.users[user]["nick"], "type": "leave", "data": ""}],
								 ignore=(None if force else user))
			if user in self.users and room in self.rooms:
				self.users[user]["rooms"].discard(room)
				del self.rooms[room]["users"][user]

				if len(self.rooms[room]["users"]) == 0:
					if room != self.DEFAULT_ROOM:
						del self.rooms[room]
				self.log(self.id(user), f'left "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
			elif room in self.rooms and "users" in self.rooms[room]:
				self.log(self.id(user), f'failed to leave "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
				await self.system(user, 401)
			else:
				self.log(self.id(user), f'failed to leave "{room}"', 2)
				await self.system(user, 401)
			self.dump(user, room, "leave", "")

		async def switch(self, user, room):
			''' Leave all other rooms and join new one '''
			if user not in self.users:
				return
			for old_room in self.users[user]["rooms"].copy():
				await self.leave(user, old_room)
			await self.join(user, room)

		async def list_users(self, user, room):
			''' Send list of users in room for a single user (user has to be in that room) '''
			if room and user in self.users and room in self.rooms:
				nicks = sorted([self.rooms[room]["users"][con]["nick"] for con in self.rooms[room]["users"]], key=str.lower)
				await self.send(user, room, [{"user": nick, "type": "join", "data": ""} for nick in nicks])
			else:
				self.log(self.id(user), f'failed to list users in "{room}" ({len(self.rooms[room]["users"].keys())})', 2)
				await self.system(user, 401)

		async def list_rooms(self, user):
			''' List available rooms for a single user as system message (does not have to be in a room) '''
			if user in self.users:
				# rooms = sorted([room for room in self.rooms], key=str.lower)
				detail = {room: self.rooms[room]["title"] for room in self.rooms}
				await self.system(user, 212, "", detail)
			else:
				self.log(self.id(user), f'failed to list rooms', 2)
				await self.system(user, 401)

		def in_room(self, user, room):
			''' True if user in that room, False otherwise '''
			if user in self.users:
				if room in self.rooms:
					return user in self.rooms[room]["users"]
			return False

		### handle sending messages

		def _create_payload(self, room, payload, check=True):
			''' Create a payload for sending user messages '''
			if type(payload) is not list:
				payload = [payload]
			return {
				"info": "user",
				"room": room,
				"payload": [self._validate_out(p) if check else p for p in payload]
			}

		async def post(self, user, message):
			''' Force send any message to a single user through websocket connection '''
			try:
				if user in self.users:
					await user.send(json.dumps(message))
			except Exception as e:
				self.log(f"Unable to send to {self.id(user)}: {e}", 1)

		async def send(self, user, room, payload):
			''' Make sure payload is valid, then send it to a single user in a room '''
			if room in self.rooms and user in self.users:
				await self.post(user, self._create_payload(room, payload))

		async def system(self, user, code=200, msg="", detail={}):
			''' Send system message (including errors) to user (does not need to be in a room) '''
			if user in self.users:
				payload = {
					"info": ("system" if (code >= 100 and code < 400) else "error"),
					"response": {
						"time": self.now(),
						"code": code,
						"msg": (msg if msg else self._get_system_message(code)),
						"detail": detail
					}
				}
				await self.post(user, payload)

		async def broadcast(self, room, payload, ignore=None):
			''' Make sure payload is valid, then send it to all users in room (except to optinal ignore=user) '''
			if room in self.rooms:
				message = self._create_payload(room, payload)
				for recipient in self.rooms[room]["users"]:
					if recipient in self.users and self.users[recipient]["auth"] and recipient != ignore:
						await self.post(recipient, message)

		async def headsets(self):
			''' Send all headset data to all users in all rooms (called on tics) '''
			for room in self.rooms:
				all_transforms = []
				for recipient in self.rooms[room]["users"]:
					all_transforms.append({
						"user": self.rooms[room]["users"][recipient]["nick"],
						"type": "transform",
						"data": self.rooms[room]["users"][recipient]["transform"]
					})
					self.dump(recipient, room, "transform", self.rooms[room]["users"][recipient]["transform"])
				if all_transforms:
					await self.broadcast(room, all_transforms)

		def history(self, room, payload=None):
			''' Returns room history as list of events. If payload is set, appends it to history first. '''
			if room in self.rooms:
				if payload is not None:
					self.rooms[room]["history"].append(payload)
					self.rooms[room]["history"] = self.rooms[room]["history"][-self.rooms[room]["size"]:]
				return self.rooms[room]["history"]
			else:
				return []


if __name__ == "__main__":
	server = Server(log_file=f"logs/log_{Server.now('%Y-%m-%d_%H-%M-%S')}.csv")
	server.run()
