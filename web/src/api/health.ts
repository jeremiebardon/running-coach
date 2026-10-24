import { useQuery } from "@tanstack/react-query";
import type { components } from "./schema";

export type Health = components["schemas"]["Health"];

async function fetchHealth(): Promise<Health> {
  const res = await fetch("/health");
  if (!res.ok) throw new Error(`GET /health -> ${res.status}`);
  return res.json();
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: fetchHealth });
}
