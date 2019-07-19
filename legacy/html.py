#!/usr/bin/env python

import time
import json
import asyncio
import websockets
from socket import gethostbyname, gethostname


class Server:

		DEFAULT_ROOM = "lobby"
		DEFAULT_HISTORY = 100

		def __init__(self, ip="", port=42069):
			self.ip = ip if ip else gethostbyname(gethostname())
			self.port = port
			self.rooms = {}
			self.open(self.DEFAULT_ROOM)
			self.users = {}
			self.loop = asyncio.get_event_loop()
			self.service = None

		# start server
		def run(self):
			self.service = websockets.serve(self._connection, self.ip, self.port)
			self.log(f"Server starting at {self.ip}:{self.port}")
			try:
				self.loop.run_until_complete(self.service)
				self.loop.run_forever()
			except KeyboardInterrupt:
				self.log("Closing server.")
				self.loop.close()

		@staticmethod
		def log(msg):
			print(f'{time.strftime("%H:%M:%S")} > {msg}')

		@staticmethod
		def validate(data):
			result = {}
			for must in ("room", "data"):
				if must not in data:
					raise KeyError(f"payload missing key {must}")
				result[must] = data[must]
			result["cmd"] = data["cmd"] if "cmd" in data else "msg"
			result["time"] = data["time"] if "time" in data else time.time()
			return result

		def _er(self, e, user=None):
			errors = {
				"invalid_data": ("Invalid data.", 400),
				"invalid_protocol": ("Invalid protocol.", 405),
				"invalid_structure": ("Invalid data structure.", 406),
				"payload_too_big": ("Payload too large.", 413),
				"not_logged_in": ("Please log in first.", 401),
				"not_in_room": ("Please join the room first.", 401),
				"access_denied": ("Access denied.", 401),
				"user_kicked": ("Forced to leave room.", 401),
				"user_banned": ("You are banned from this room.", 403),
				"ip_banned": ("You are banned from this room.", 403),
				"not_implemented": ("Unknown request.", 501),
				"internal_error": ("Internal Server Error.", 500),
				"unknown_error": ("Internal Server Error.", 418)
			}
			if e not in errors:
				e = "unknown_error"
			if user is not None:
				self.log(f"ERROR: {user} > {errors[e][0]}")
			return errors[e]

		async def _connection(self, user, path):
			# connect user
			self.connect(user)
			self.log(f'{self.id(user)} connected')
			try:
				# wait for data from user once the connection is established
				while True:
					try:
						message = json.loads(await user.recv())
						message["time"] = time.time()
						self.users[user]["updated"] = message["time"]

						# is user logged in?
						if self.users[user]["nick"]:
							try:
								message = self.validate(message)
							except KeyError as e:
								await self.system(user, self._er("invalid_structure", self.id(user)))
								continue

							# system commands
							if message["room"] == self.SERVER_NAME:
								if message["cmd"] == "ping":
									await self.system(user, message, "pong")
								elif message["cmd"] == "join":
									# system response sent by join() based on success
									await self.join(user, message, message["data"])
								elif message["cmd"] == "leave":
									await self.system(user, message, "Left room.")
									await self.leave(user, message["data"])
								else:
									await self.system(user, message, *self._er("not_implemented"))

							# messages sent to rooms
							elif self.in_room(user, message["room"]):
								if message["cmd"] in ("msg",):
									self.history(message["room"], {"user": self.users[user]["nick"], **message})
								await self.broadcast(user, message["room"], {"cmd": message["cmd"], "data": message["data"]})
							else:
								await self.system(user, message, *self._er("not_in_room"))
						else:
							# look for credentials
							if "cmd" in message and message["cmd"] == "login":
								await self.login(user, message)
							else:
								await self.system(user, message, *self._er("not_logged_in"))
					except json.decoder.JSONDecodeError:
						await self.system(user, {}, *self._er("invalid_data", self.id(user)))
						continue

			# disconnect user
			except websockets.ConnectionClosed:
				self.log(f'{self.id(user)} disconnected')
			except websockets.WebSocketProtocolError:
				await self.system(user, {}, *self._er("invalid_protocol", self.id(user)))
			except websockets.PayloadTooBig:
				await self.system(user, {}, *self._er("payload_too_big", self.id(user)))
			except Exception as e:
				self.log(f"Unknown Exception: {e}")
				await self.system(user, {}, *self._er("internal_error"))
			finally:
				try:
					await self.disconnect(user)
				except Exception as e:
					del self.users[user]
					self.log(f'Failed to safely disconnect: {e}')

		def id(self, user):
			if not self.users[user]["nick"]:
				return f'{self.users[user]["ip"]}'
			return f'{self.users[user]["nick"]} ({self.users[user]["ip"]})'

		# create user data when connection is established
		def connect(self, user, data={}):
			if user in self.users:
				return
			default = {
				"nick": "",
				"level": "user",
				"status": "online",
				"connected": time.time(),
				"updated": time.time(),
				"ip": (user.remote_address[0] if user.remote_address else "0.0.0.0"),
				"rooms": set(),
				"meta": {}
			}
			self.users[user] = {**default, **data}

		# remove user data when connection is closed
		async def disconnect(self, user):
			if user in self.users:
				for room in self.users[user]["rooms"].copy():
					await self.leave(user, room)
				del self.users[user]

	# user sends credentials
		async def login(self, user, payload):
			if user in self.users:
				if "data" in payload and type(payload["data"]) is dict:
					if "user" in payload["data"]:
						if payload["data"]["user"] != self.admin:
							# TODO: do actual credential check
							self.users[user]["nick"] = payload["data"]["user"]
							self.log(f"{self.id(user)} logged in")
							await self.system(user, payload, "Access granted.")
							return
			await self.system(user, payload, *self._er("access_denied"))

		# open a new room
		def open(self, room, payload={}):
			if room == self.SERVER_NAME:
				return
			if room in self.rooms:
				return
			default = {
				"history": [],
				"topic": "",
				"welcome": "",
				"created": time.time(),
				"users": set(),
				"nicks": set(),
				"size": self.DEFAULT_HISTORY,
				"blacklist": {
					"ips": {},
					"nicks": {}
				},
			}
			self.rooms[room] = {**default, **payload}

		# close an existing room
		async def close(self, room):
			if room in (self.SERVER_NAME, self.DEFAULT_ROOM):
				return
			if room in self.rooms:
				for user in self.users:
					await self.leave(user, room, True)
				del self.rooms[room]

		# join an existing room
		async def join(self, user, message, room):
			if user in self.users:
				if not self.users[user]["nick"]:
					await self.system(user, message, *self._er("not_logged_in"))
					return
				if room not in self.rooms:
					self.open(room)
				if self.users[user]["nick"] in self.rooms[room]["blacklist"]["nicks"]:
					await self.system(user, message, *self._er("user_banned"))
					return
				elif self.users[user]["ip"] in self.rooms[room]["blacklist"]["ips"]:
					await self.system(user, message, *self._er("ip_banned"))
					return
				self.users[user]["rooms"].add(room)
				self.rooms[room]["users"].add(user)
				self.rooms[room]["nicks"].add(self.users[user]["nick"])
				# send history to user
				await self.system(user, message, "Joined room.") #TODO: send self.history(room)
				# broadcast to everyone but the user
				await self.broadcast(user, room, {"cmd": "join", "data": ""})

		async def leave(self, user, room, force=False):
			if user in self.users:
				if room in self.rooms:
					self.users[user]["rooms"].discard(room)
					self.rooms[room]["users"].discard(user)
					self.rooms[room]["nicks"].discard(self.users[user]["nick"])
					if len(self.rooms[room]["users"]) == 0:
						await self.close(room)
					if not force:
						# broadcast to everyone but the user
						await self.broadcast(user, room, {"cmd": "leave", "data": ""})
					else:
						await self.send(user, room, {"cmd": "kick", "data": ""})

		def in_room(self, user, room):
			if user in self.users:
				if room in self.rooms:
					return user in self.rooms[room]["users"]
			return False

		# handle sending messages

		# send payload to user
		async def post(self, user, payload):
			payload["time"] = time.time()
			try:
				await user.send(json.dumps(payload))
			except Exception as e:
				self.log(f"Unable to send to {self.id(user)}: {e}")

		# send to user only
		async def send(self, user, room, payload):
			payload["room"] = room
			payload["user"] = self.users[user]["nick"]
			if "cmd" not in payload:
				payload["cmd"] = "msg"
			await self.post(user, payload)

		# send user's payload to everyone (sometimes to the user as well)
		async def broadcast(self, user, room, payload, all=True):
			if room in self.rooms:
				if self.users[user]["nick"]:
					if len(self.rooms[room]["users"]):
						payload["room"] = room
						payload["user"] = self.users[user]["nick"]
						if "cmd" not in payload:
							payload["cmd"] = "msg"
						if "data" not in payload:
							payload["data"] = ""
						for recipient in self.rooms[room]["users"]:
							if not all and recipient == user:
								continue
							await self.post(recipient, payload)

		# send system message directly to user (NOTE: takes msg data instead of payload)
		async def system(self, user, msg, code=200, args=None):
			new_payload = {
				"room": self.SERVER_NAME,
				"user": self.admin,
				"cmd": "info",
				"data": {
					"code": code,
					"message": msg,
					"args": args
				}
			}
			await self.post(user, new_payload)

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
