# Frontend

React + TypeScript + Ant Design + Leaflet frontend for the imagery hub.

## Install

```powershell
cd frontend
npm.cmd install
```

## Run

```powershell
cd frontend
npm.cmd run dev
```

The backend API defaults to `http://localhost:8000`. Override it with `VITE_API_BASE_URL`.

地图页在配置 `VITE_TIANDITU_TOKEN` 后使用天地图电子地图和影像地图；未配置时自动使用 OpenStreetMap 作为备用底图。
