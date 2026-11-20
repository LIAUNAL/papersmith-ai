import type { AddressInfo } from "node:net";
import type { Server } from "node:http";
import { createAdaptorServer } from "@hono/node-server";
import type { ListenFn } from "./listen.ts";

/** The real listener: a Node HTTP server running the Hono `fetch` handler. */
export const nodeListen: ListenFn = ({ port, hostname, fetch }) =>
  new Promise((resolve, reject) => {
    const server = createAdaptorServer({ fetch }) as Server;
    server.once("error", reject);
    server.listen(port, hostname, () => {
      server.off("error", reject);
      resolve({
        port: (server.address() as AddressInfo).port,
        close: () =>
          new Promise<void>((done) => {
            server.close(() => done());
            server.closeAllConnections();
          }),
      });
    });
  });
