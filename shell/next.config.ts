import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: new URL("..", import.meta.url).pathname,
  reactStrictMode: true,
  transpilePackages: ["@openarga/ui"],
};

export default config;
