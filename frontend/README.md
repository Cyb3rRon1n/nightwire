# Nightwire web client

Next.js app for playing Nightwire. All game logic lives in the Python server
(`../server`); this client only talks to it over WebSocket
(`NEXT_PUBLIC_NIGHTWIRE_WS_URL`, default `ws://localhost:8000`).

```bash
npm install
npm run dev            # http://localhost:3000 → /nightwire
npm run lint && npm run build
npm run test:nightwire # node --test over tests/nightwire
```

- `src/app/nightwire/` — the play screen (feed, status, world, phone, gallery).
- `src/lib/nightwire/` — protocol types, socket hook, reducer, feed helpers.
- `image_server/` — the optional `flux_worker` image backend
  (`IMAGE_BACKEND=flux_worker`, `npm run image:server`); see its README.
  Not needed with `IMAGE_BACKEND=comfyui`.

Started as a fork of [open-dungeon](https://github.com/newideas99/open-dungeon)
(MIT, see `LICENSE`); its own app has been removed.
