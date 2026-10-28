/** Proxy API requests to the local backend; browser uses a single origin. */
const config = { output: process.env.KNOWGPT_STANDALONE === '1' ? 'standalone' : undefined, experimental: { proxyTimeout: 300000, workerThreads: process.env.KNOWGPT_WORKER_THREADS === '1', webpackBuildWorker: false, cpus: 2 }, async rewrites() { return [{ source: '/api/:path*', destination: `${process.env.API_URL || 'http://127.0.0.1:8000'}/api/:path*` }]; } };
export default config;
