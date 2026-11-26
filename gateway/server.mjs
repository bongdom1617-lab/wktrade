#!/usr/bin/env node
/**
 * GOLD AI Single-Origin Reverse Proxy Gateway (HTTP + WebSocket)
 *
 * Exposes both the Next.js frontend (:3000) and FastAPI REST + WebSocket backend (:8000)
 * behind ONE local port (:8080) so Cloudflare Tunnel (Quick Tunnel or Named Tunnel)
 * routes everything over a single HTTPS/WSS origin with zero CORS or mixed-content issues.
 */

import http from "node:http";
import net from "node:net";

const LISTEN_HOST = process.env.GATEWAY_HOST || "127.0.0.1";
const LISTEN_PORT = Number(process.env.GATEWAY_PORT || 8095);
const BACKEND_HOST = process.env.BACKEND_HOST || "127.0.0.1";
const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8000);
const FRONTEND_HOST = process.env.FRONTEND_HOST || "127.0.0.1";
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || 3000);

function isBackendPath(urlPath = "/") {
  return (
    urlPath.startsWith("/api/") ||
    urlPath === "/api" ||
    urlPath.startsWith("/ws/") ||
    urlPath === "/ws" ||
    urlPath === "/docs" ||
    urlPath.startsWith("/docs/") ||
    urlPath === "/redoc" ||
    urlPath === "/openapi.json"
  );
}

const server = http.createServer((clientReq, clientRes) => {
  const urlPath = clientReq.url || "/";
  const toBackend = isBackendPath(urlPath);
  const targetHost = toBackend ? BACKEND_HOST : FRONTEND_HOST;
  const targetPort = toBackend ? BACKEND_PORT : FRONTEND_PORT;

  const headers = { ...clientReq.headers };
  headers["x-forwarded-host"] = clientReq.headers.host || `${LISTEN_HOST}:${LISTEN_PORT}`;
  headers["x-forwarded-proto"] = clientReq.headers["x-forwarded-proto"] || "http";
  headers.host = `${targetHost}:${targetPort}`;

  const proxyReq = http.request(
    {
      hostname: targetHost,
      port: targetPort,
      path: urlPath,
      method: clientReq.method,
      headers,
    },
    (proxyRes) => {
      clientRes.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(clientRes, { end: true });
    }
  );

  proxyReq.on("error", (err) => {
    if (!clientRes.headersSent) {
      clientRes.writeHead(502, { "Content-Type": "application/json" });
      clientRes.end(
        JSON.stringify({
          error: "upstream_unavailable",
          target: toBackend ? "backend:8000" : "frontend:3000",
          detail: err.message,
        })
      );
    } else {
      clientRes.end();
    }
  });

  clientReq.on("aborted", () => proxyReq.destroy());
  clientReq.pipe(proxyReq, { end: true });
});

// Transparent bidirectional WebSocket upgrade tunneling (/ws/market -> FastAPI :8000)
server.on("upgrade", (req, clientSocket, head) => {
  const urlPath = req.url || "/";
  const toBackend = isBackendPath(urlPath);
  const targetHost = toBackend ? BACKEND_HOST : FRONTEND_HOST;
  const targetPort = toBackend ? BACKEND_PORT : FRONTEND_PORT;

  const upstream = net.connect(targetPort, targetHost, () => {
    let rawReq = `${req.method || "GET"} ${urlPath} HTTP/${req.httpVersion || "1.1"}\r\n`;
    const rawHeaders = req.rawHeaders || [];
    for (let i = 0; i < rawHeaders.length; i += 2) {
      const k = rawHeaders[i];
      const v = rawHeaders[i + 1];
      if (k.toLowerCase() === "host") {
        rawReq += `Host: ${targetHost}:${targetPort}\r\n`;
      } else {
        rawReq += `${k}: ${v}\r\n`;
      }
    }
    rawReq += "\r\n";

    upstream.write(rawReq);
    if (head && head.length > 0) {
      upstream.write(head);
    }

    upstream.pipe(clientSocket);
    clientSocket.pipe(upstream);
  });

  const cleanup = () => {
    if (!upstream.destroyed) upstream.destroy();
    if (!clientSocket.destroyed) clientSocket.destroy();
  };

  upstream.on("error", cleanup);
  clientSocket.on("error", cleanup);
  upstream.on("close", () => {
    if (!clientSocket.destroyed) clientSocket.end();
  });
  clientSocket.on("close", () => {
    if (!upstream.destroyed) upstream.end();
  });
});

server.listen(LISTEN_PORT, LISTEN_HOST, () => {
  console.log(
    `[GOLD AI Gateway] Listening on http://${LISTEN_HOST}:${LISTEN_PORT} -> frontend :${FRONTEND_PORT}, backend :${BACKEND_PORT}`
  );
});
