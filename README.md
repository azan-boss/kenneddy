# Kennedy Moon Grill — Backend API & AI Voice Agent 🌙

Production-ready Django REST backend with Daphne ASGI, Channels (WebSockets), Redis, PostgreSQL, and ElevenLabs Conversational AI voice ordering integration.

## 🚀 Features
- **ElevenLabs AI Voice Ordering**: Real-time voice agent integration (`/api/orders/voice-order/` and `/api/orders/voice-status/`).
- **Live Real-time WebSockets**: Kitchen KDS console & live rider GPS tracking map.
- **Menu Book API**: Structured dish variants, pricing, and category endpoints.
- **Railway & Docker Ready**: Native support for Nixpacks, Procfile, Daphne, WhiteNoise, and PostgreSQL.

## 🛠️ Tech Stack
- **Framework**: Django 6.1 + Django REST Framework + Channels 4
- **ASGI Server**: Daphne
- **Database**: PostgreSQL (with `dj-database-url`)
- **Cache & Layers**: Redis 7
- **Static Assets**: WhiteNoise
