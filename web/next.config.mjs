/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: {
    // Static export can't use the optimizing image loader.
    unoptimized: true,
  },
};

export default nextConfig;
