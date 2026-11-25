import type { StoreError } from "@caztor/core";
import type { Context } from "hono";
import { errorResponse, type ErrorStatus } from "./http.ts";

export interface DescribedError {
  status: ErrorStatus;
  body: { error: string; message: string; path: string; currentHash?: string | null };
}

/** The HTTP status and a readable body for a typed store error. Raw system messages are never exposed. */
export function describeStoreError(error: StoreError): DescribedError {
  const path = error.path;
  const named = (status: ErrorStatus, message: string): DescribedError => ({
    status,
    body: { error: error.code, message, path },
  });
  switch (error.code) {
    case "not_found":
      return named(404, `"${path}" was not found.`);
    case "invalid_path":
      return named(400, `"${path}" is not a valid project path.`);
    case "outside_root":
      return named(403, `"${path}" is outside the project.`);
    case "hidden":
      return named(403, `"${path}" is reserved and cannot be used.`);
    case "exists":
      return named(409, `"${path}" already exists. Choose another name.`);
    case "too_large":
      return named(413, `"${path}" is too large to open in the editor.`);
    case "not_text":
      return named(415, `"${path}" is not a UTF-8 text file.`);
    case "io":
      return named(500, `"${path}" could not be read or written.`);
    case "conflict":
      return {
        status: 409,
        body: {
          error: "conflict",
          message: `"${path}" changed on disk since it was opened.`,
          path,
          currentHash: error.currentHash,
        },
      };
  }
}

export function storeErrorResponse(c: Context, error: StoreError): Response {
  const { status, body } = describeStoreError(error);
  const { error: code, message, ...extra } = body;
  return errorResponse(c, status, code, message, extra);
}
