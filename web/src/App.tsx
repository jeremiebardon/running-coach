import { useHealth } from "@/api/health";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

const sourceBlurb: Record<string, string> = {
  fixtures: "Pretend miles from a demo athlete. Great for testing, terrible for bragging.",
  intervals: "Your real miles, straight from intervals.icu. No excuses now.",
};

export default function App() {
  const health = useHealth();

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-6">
      <h1 className="text-3xl font-semibold">Your running coach</h1>
      <Card>
        {health.isPending && <CardDescription>Warming up, hang tight…</CardDescription>}
        {health.isError && (
          <>
            <CardTitle>Hit a wall</CardTitle>
            <CardDescription>The coach isn't answering. Is the API running on :3000?</CardDescription>
          </>
        )}
        {health.data && (
          <>
            <CardTitle className="flex items-center gap-2">
              Coach is awake <Badge variant="secondary">{health.data.dataSource}</Badge>
            </CardTitle>
            <CardDescription>
              {sourceBlurb[health.data.dataSource] ?? `Reading miles from ${health.data.dataSource}.`}
            </CardDescription>
          </>
        )}
      </Card>
    </main>
  );
}
