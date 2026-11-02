import {defineConfig} from 'vite'; import react from '@vitejs/plugin-react';
// Dev server forwards /api to the FastAPI backend so the app can use same-origin URLs everywhere.
export default defineConfig({plugins:[react()],server:{proxy:{'/api':process.env.VITE_DEV_API_TARGET||'http://localhost:8000'}}});
