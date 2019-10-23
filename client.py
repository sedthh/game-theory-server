#!/usr/bin/env python

import asyncio
import websockets
import json
from datetime import datetime

async def hello():
    async with websockets.connect(f'ws://192.168.0.241:42069') as ws:
        msg = [
            {"room": "lobby", "type": "msg", "data": "this will fail because I am not logged in"},
            {"system": "login", "options": {"user": "Tibi", "pass": "1234"}},
            {"system": "ping"},
            {"room": "test", "type": "join", "data": ""},
            {"system": "rooms"},
            {"room": "lobby", "type": "msg", "data": "hello"},
            {"room": "lobby", "type": "transform", "data": {
                "pos": {
                    "x": 7.0,
                    "y": 8.0,
                    "z": 9.0
                },
                "rot": {
                    "x": 4.0,
                    "y": 5.0,
                    "z": 6.0
                }
            }},
            {"room": "lobby", "type": "msg", "data": "hello again"},
            {"room": "lobby", "type": "leave", "data": ""},
            {"room": "lobby", "type": "msg", "data": "this will also fail"},
        ]
        for m in msg:
            await ws.send(json.dumps(m))
            print(json.loads(await ws.recv()))
        await ws.send(json.dumps(m))
        print(datetime.timestamp(datetime.now()))
        print(json.loads(await ws.recv()))
        await ws.send(json.dumps(m))
        print(datetime.timestamp(datetime.now()))
        print(json.loads(await ws.recv()))

print(datetime.timestamp(datetime.now()))
asyncio.get_event_loop().run_until_complete(hello())


