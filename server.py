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

		def __init__(self, ip="", port=42069, fps=1):
			self.ip = ip if ip else gethostbyname(gethostname())
			self.port = port
			self.frequency = 1.0/fps

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

		@staticmethod
		def log(user, msg=None):
			if msg is None:
				user, msg = "", user
			print(f'{time.strftime("%H:%M:%S")} > {user}{msg}')

		@staticmethod
		def _validate_in(payload):
			result = {}
			for must in ("room", "data"):
				if must not in payload:
					raise KeyError(f"payload missing key {must}")
				result[must] = payload[must]
			result["cmd"] = payload["cmd"] if "cmd" in payload else "msg"
			result["time"] = payload["time"] if "time" in payload else time.time()
			return result

		@staticmethod
		def _validate_out(payload):
			return {
				"time": payload["time"] if "time" in payload else time.time(),
				"user": payload["user"] if "user" in payload else "",
				"cmd": payload["cmd"] if "cmd" in payload else "msg",
				"data": payload["data"] if "data" in payload else ""
			}

		@staticmethod
		def _validate_transform(payload):
			if "transform" not in payload:
				payload["transform"] = {}
			for key in ("pos", "rot"):
				if key not in payload["transform"]:
					payload["transform"][key] = {}
				for cord in ("x", "y", "z"):
					if cord not in payload["transform"][key]:
						payload["transform"][key][cord] = 0
			return {key:payload["transform"][key] for key in ("pos", "rot")}

		def id(self, user):
			if not self.users[user]["nick"]:
				return f'{self.users[user]["ip"]} '
			return f'{self.users[user]["nick"]} ({self.users[user]["ip"]}) '

		async def _connection(self, user, path):
			# connect user
			self.connect(user)
			self.log(self.id(user), 'trying to connect')
			try:
				# wait for data from user once the connection is established
				while True:
					try:
						self.users[user]["updated"] = time.time()
						message = json.loads(await user.recv())

						if not self.users[user]["auth"]:
							# log in with credentials
							if "login" in message:
								# TODO: do actual authentication later
								if "user" in message["login"]:
									self.users[user]["nick"] = message["login"]["user"]
									self.users[user]["auth"] = True
									self.log(self.id(user), 'logged in')
									await self.join(user, self.DEFAULT_ROOM)
						else:
							# check payload
							try:
								message = self._validate_in(message)
							except KeyError as e:
								self.log(self.id(user), 'sent invalid data')
								continue
							if message["cmd"] == "transform":
								self.users[user]["transform"] = self._validate_transform(message)
							elif message["cmd"] == "join":
								await self.join(user, message["room"])
							elif message["cmd"] == "leave":
								await self.leave(user, message["room"])
							else:
								self.history(message["room"], self._validate_out({"user": self.users[user]["nick"], **message}))

					except json.decoder.JSONDecodeError:
						self.log(self.id(user), 'sent malformed JSON')
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
				"cache": [],
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
				"users": set(),
				"nicks": set(),
				"history": [],
				"size": self.DEFAULT_HISTORY
			}
			self.rooms[room] = {**default, **payload}

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
				self.rooms[room]["users"].add(user)
				self.rooms[room]["nicks"].add(self.users[user]["nick"])
				# send history to user
				await self.send(user, room, self.history(room))
				await self.broadcast(room, [{"user": self.users[user]["nick"], "cmd": "join", "data": ""}])

		async def leave(self, user, room, force=False):
			if room and user in self.users and room in self.rooms:
				await self.broadcast(room, [{"user": self.users[user]["nick"], "cmd": "leave", "data": ""}], ignore=(None if force else user))
				self.users[user]["rooms"].discard(room)
				self.rooms[room]["users"].discard(user)
				self.rooms[room]["nicks"].discard(self.users[user]["nick"])
				if len(self.rooms[room]["users"]) == 0:
					if room != self.DEFAULT_ROOM:
						del self.rooms[room]

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
				"room": room,
				"data": [self._validate_out(p) if check else p for p in payload]
			}

		# send payload as it is to user through websocket connection
		async def post(self, user, message):
			try:
				if user in self.users:
					await user.send(json.dumps(message))
			except Exception as e:
				self.log(f"Unable to send to {self.id(user)}: {e}")

		# extend and send payload to a single user in a room
		async def send(self, user, room, payload):
			if room in self.rooms and user in self.users:
				await self.post(user, self._create_payload(room, payload))

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
						"user": self.users[recipient]["nick"],
						"cmd": "transform",
						"data": self.users[recipient]["transform"]
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
