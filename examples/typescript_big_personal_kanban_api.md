# TypeScript Big Task — Personal Kanban API

## Difficulty
Big

## Goal
Build a small TypeScript backend API for a personal Kanban board.

## What You Will Build
A Node.js TypeScript API called `kanban-core`.

## Core Features

Users can create boards, columns, and cards.

Default columns:

```text
todo
doing
done
```

## Data Models

### Board

```ts
type Board = {
  id: string;
  name: string;
  createdAt: string;
};
```

### Column

```ts
type Column = {
  id: string;
  boardId: string;
  name: string;
  position: number;
};
```

### Card

```ts
type Card = {
  id: string;
  boardId: string;
  columnId: string;
  title: string;
  description?: string;
  position: number;
  createdAt: string;
  updatedAt: string;
};
```

## Required Endpoints

Implement:

```text
GET    /boards
POST   /boards
GET    /boards/:boardId
DELETE /boards/:boardId

GET    /boards/:boardId/cards
POST   /boards/:boardId/cards
PATCH  /cards/:cardId
DELETE /cards/:cardId

POST   /cards/:cardId/move
```

## Requirements

1. Use TypeScript throughout.
2. Use Express, Fastify, or another Node HTTP framework.
3. Store data in memory first.
4. Validate request bodies.
5. Return useful HTTP status codes.
6. Add centralized error handling.
7. Add a simple logger.
8. Document the API in `README.md`.

## Acceptance Criteria

- Creating a board creates default columns.
- Cards can be moved between columns.
- Card ordering is preserved with `position`.
- Invalid board/card IDs return `404`.
- Invalid request bodies return `400`.
- Server can be started with `npm run dev`.
- Code is split into routes, services, models, and validation.

## Suggested Project Structure

```text
kanban-core/
├── package.json
├── tsconfig.json
├── README.md
└── src/
    ├── server.ts
    ├── routes/
    ├── services/
    ├── models/
    ├── validation/
    └── errors/
```

## Stretch Goals

- Add SQLite persistence.
- Add OpenAPI docs.
- Add tests with Supertest.
- Add drag-and-drop ordering logic.
- Add simple token-based auth.
