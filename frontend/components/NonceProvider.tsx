"use client";

import { createContext, useContext, type ReactNode } from "react";

const NonceContext = createContext<string | undefined>(undefined);

export function NonceProvider({
  nonce,
  children,
}: {
  nonce?: string;
  children: ReactNode;
}) {
  return (
    <NonceContext.Provider value={nonce}>{children}</NonceContext.Provider>
  );
}

/** CSP nonce from proxy.ts (undefined in tests that skip proxy). */
export function useNonce(): string | undefined {
  return useContext(NonceContext);
}
