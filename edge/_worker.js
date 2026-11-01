/**
 * Cloudflare Edge Worker & Gateway: ResIPy Geophysics & GPS Platform
 * Dikelola oleh Tim 5: Deployment, Cloudflare & GitHub CI/CD (Phiseis)
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // =========================================================================
    // 1. CORS PREFLIGHT HANDLING
    // Mengizinkan komunikasi cross-origin jika frontend diakses via domain/subdomain
    // =========================================================================
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // =========================================================================
    // 2. EDGE CACHING UNTUK ASET 3D & MODEL VOLUMETRIK
    // Mengoptimalkan pengiriman berkas .gltf, .bin, .vtk, dan peta DEM
    // =========================================================================
    const is3dAsset = url.pathname.endsWith(".gltf") || 
                      url.pathname.endsWith(".bin") || 
                      url.pathname.endsWith(".vtk") ||
                      url.pathname.endsWith(".tif");

    // =========================================================================
    // 3. ZERO TRUST CLUSTER PROXY ROUTING
    // Merutekan request /api/* ke Microservices Klaster (via Cloudflare Tunnel)
    // =========================================================================
    if (url.pathname.startsWith("/api/")) {
      // Jika CLUSTER_API_ORIGIN dikonfigurasi, teruskan traffic ke tunnel backend
      const clusterOrigin = env.CLUSTER_INTERNAL_API || "http://127.0.0.1:8050";
      
      try {
        const targetUrl = new URL(url.pathname + url.search, clusterOrigin);
        const forwardRequest = new Request(targetUrl.toString(), {
          method: request.method,
          headers: request.headers,
          body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
          redirect: "follow",
        });

        const clusterResponse = await fetch(forwardRequest);
        const respHeaders = new Headers(clusterResponse.headers);
        respHeaders.set("Access-Control-Allow-Origin", "*");
        respHeaders.set("X-Served-By", "Phiseis-Cloudflare-Gateway");

        return new Response(clusterResponse.body, {
          status: clusterResponse.status,
          statusText: clusterResponse.statusText,
          headers: respHeaders,
        });
      } catch (err) {
        return new Response(JSON.stringify({
          error: "Cluster Gateway Unavailable",
          detail: "Gagal menghubungkan ke backend klaster geofisika.",
          hint: "Pastikan Cloudflare Tunnel dan service backend aktif."
        }), {
          status: 502,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
          }
        });
      }
    }

    // =========================================================================
    // 4. FRONTEND STATIC ASSETS & SECURITY HEADERS
    // =========================================================================
    const response = await env.ASSETS.fetch(request);
    const newHeaders = new Headers(response.headers);

    // Hardening Keamanan Web
    newHeaders.set("X-Frame-Options", "SAMEORIGIN");
    newHeaders.set("X-Content-Type-Options", "nosniff");
    newHeaders.set("Referrer-Policy", "strict-origin-when-cross-origin");
    newHeaders.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload");

    // Cache rules untuk aset 3D & statis
    if (is3dAsset) {
      newHeaders.set("Cache-Control", "public, max-age=604800, immutable");
    } else if (url.pathname.endsWith(".html") || url.pathname === "/") {
      newHeaders.set("Cache-Control", "no-cache, must-revalidate");
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: newHeaders,
    });
  },
};
