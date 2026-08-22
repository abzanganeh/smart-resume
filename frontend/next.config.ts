import type { NextConfig } from "next";
import { securityResponseHeaders } from "./lib/securityHeaders";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["192.168.88.24"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityResponseHeaders(),
      },
    ];
  },
};

export default nextConfig;
