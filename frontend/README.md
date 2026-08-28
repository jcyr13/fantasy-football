# frontend

React + Vite + TypeScript SPA for the Dead Parrots Dashboard. Presentation and
interaction only — no scoring or projection math
(see `../docs/adr/0003-python-for-numeric-logic-react-presentation-only.md`).

## Develop

```sh
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:8000
npm run lint
npm run build
```

The scaffold renders one screen that calls `GET /api/health` and shows the
result. The six real screens and the news ticker arrive in tickets #17–#18.
