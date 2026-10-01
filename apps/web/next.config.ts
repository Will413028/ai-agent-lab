import type { NextConfig } from "next";

const config: NextConfig = {
  compress: false,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:18761/:path*" }];
  },
};

export default config;
