# Frontend

React + TypeScript application providing the user interface for job search, application management, and pipeline execution.

## Pages

| Route | Component | Description |
|---|---|---|
| `/` | Dashboard | System status, profile summary, application metrics, quick actions |
| `/profile` | Profile | CV upload form, AI-extracted profile display (skills, domains, seniority, gaps) |
| `/jobs` | Job Search | Search form, results list, job detail view, inline application generation |
| `/applications` | Applications | Application tracking table with status transitions and metrics bar |
| `/pipeline` | Full Pipeline | End-to-end agent pipeline runner with step visualization and application viewer |

## Package structure

```text
src/
├── api/
│   └── client.ts       # Typed API client for all backend endpoints
├── features/
│   ├── dashboard/      # DashboardPage
│   ├── profile/        # ProfilePage
│   ├── jobs/           # JobsPage
│   ├── applications/   # ApplicationsPage
│   └── pipeline/       # PipelinePage
├── styles/
│   └── global.css      # Design system (variables, layout, components)
├── App.tsx             # Router + nav shell
└── main.tsx            # Entry point with QueryClient and BrowserRouter
```

## Run locally

```bash
npm install
npm run dev
```

Expects the backend running at `http://localhost:8000`. Override with:

```bash
VITE_API_BASE_URL=http://your-api-host/api/v1 npm run dev
```

## Build for production

```bash
npm run build
```

## Type-check

```bash
npm run lint
```

## Dependencies

| Package | Purpose |
|---|---|
| `react` + `react-dom` | UI framework |
| `react-router-dom` | Client-side routing |
| `@tanstack/react-query` | Server state management, caching, mutations |
| `vite` | Build tool and dev server |
| `typescript` | Type safety |
