import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* Static by construction: no API routes, no queue, no database. The cube is
     precomputed offline and shipped as JSON — see docs/web-app-todo.md for why
     a live-solve backend is the wrong product. */
};

export default nextConfig;
