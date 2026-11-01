/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the deployed API, e.g. https://your-backend.onrender.com. Empty uses the same origin. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
