/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  /** When set, the public site mounts the live chat widget for this tenant —
   * Flywheel selling Flywheel. See examples/seed_flywheel_sales.py. */
  readonly VITE_SALES_BUSINESS_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
