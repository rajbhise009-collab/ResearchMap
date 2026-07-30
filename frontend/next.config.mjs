/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",          // static HTML export -> frontend/out (no hosting cost)
  trailingSlash: true,       // each route -> dir/index.html, works on any static host
  images: { unoptimized: true },
  reactStrictMode: true,
};
export default nextConfig;
