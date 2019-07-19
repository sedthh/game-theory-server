#!/usr/bin/env python

import asyncio
import websockets
import json


async def hello():
    async with websockets.connect(f'ws://192.168.0.241:42069') as ws:
        msg = [
            {"login": {"user": "Tibi", "pass": "1234"}},
            {"room": "lobby", "cmd": "msg", "data": "hello"},
            {"room": "main", "cmd": "join", "data": ""},
            {"room": "main", "cmd": "msg", "data": "hello"},
            {"room": "main", "cmd": "transform", "data": {
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
            }}
        ]
        for m in msg:
            await ws.send(json.dumps(m))
            print(json.loads(await ws.recv()))

asyncio.get_event_loop().run_until_complete(hello())


